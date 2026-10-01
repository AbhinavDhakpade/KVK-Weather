# AgriAura – Smart Sugarcane Advisory Platform

A full-stack rebuild of the AgriAura dashboard: **React (Vite)** frontend talking to a **Django + Django REST Framework** backend, with the pest/disease database imported directly from the provided Excel file (`table_weather___pest_disease.xlsx`) into a relational SQLite database.

```
agriaura/
├── backend/                  Django project (API + database)
│   ├── config/                project settings, root urls
│   ├── advisory/               the one Django app: models, serializers, views, admin
│   │   ├── management/commands/seed_data.py   imports the Excel file + seeds reference data
│   │   ├── data/pest_disease.xlsx              the source Excel file (copied in)
│   │   └── migrations/
│   ├── requirements.txt
│   └── manage.py
└── frontend/                 React app (Vite)
    ├── src/
    │   ├── api/                axios client
    │   ├── context/            AppSettings (lang/theme/mode) + Data (API state) contexts
    │   ├── i18n/                EN / MR / HI translation dictionary
    │   ├── components/          layout, dashboard, weather, disease, irrigation, modals
    │   ├── pages/                one component per route (Dashboard, Weather, Disease, …)
    │   └── utils/                risk-tag logic, chart config, formatting helpers
    └── package.json
```

## What this is

The original deliverable was a single static HTML file with all data hard-coded into `<script>` tags. This version separates concerns properly:

- **Database**: every disease/pest record (30 rows), irrigation rule (10 rows), farm profile, weather reading, alert, and advisory timeline item lives in SQLite, managed through Django's ORM.
- **Backend**: Django REST Framework exposes a clean JSON API (`/api/...`), including one composite `/api/dashboard/` endpoint that the frontend calls once to populate the entire dashboard home page.
- **Frontend**: a React single-page app (React Router for the 8 pages, Context API for shared state, Chart.js via `react-chartjs-2` for all charts) that mirrors every feature of the original prototype — farmer/expert mode, dark mode, EN/MR/HI language switching, the voice-guidance FAB, and all eight pages with their modals.

## Is this actually real-time?

Honestly, partially — and it's worth being precise about what that means rather than overselling it.

**What is real-time:** every weather value shown anywhere in the app (temperature, humidity, rainfall, UV, wind, sunrise/sunset, the forecast, the auto-generated alerts) is a real number from NASA POWER or Open-Meteo, not a mock. There's a **"Refresh Now" button** on the Weather page that triggers `POST /api/weather/refresh/`, which calls both APIs synchronously in that request and returns the fresh data immediately — clicking it gets you whatever NASA POWER / Open-Meteo are reporting *right now*, in real time, in the request/response cycle.

**Automatic sync, no manual intervention required:** the backend runs an in-process background scheduler (`advisory/scheduler.py`, via APScheduler) that syncs every farm on an interval — every 60 minutes by default — starting ~20 seconds after the server boots, for as long as the server process is running. You don't need cron, Celery, or anyone remembering to click "Refresh" for data to stay current. Every run (scheduled, manual, or CLI) writes a row to the `SchedulerLog` model — visible in `/admin/`, on the dashboard's Scheduler Monitoring panel (expert mode), and via `GET /api/scheduler/status/` and `GET /api/scheduler/logs/` — recording execution time, duration, records fetched/updated, duplicates skipped, retry attempts, per-API health, and any error. Each external API call retries up to `WEATHER_SYNC_MAX_RETRIES` times (default 3) with exponential backoff before that source is marked failed for the run; one farm or one source failing never blocks the others.

Configure it via environment variables:
```bash
SCHEDULER_AUTOSTART=True              # set False to disable autostart entirely
WEATHER_SYNC_INTERVAL_MINUTES=60      # how often it runs
WEATHER_SYNC_MAX_RETRIES=3            # retry attempts per API call before marking it failed
```

**What is not real-time (and isn't meant to be):** the app doesn't hold an open connection that pushes updates to your screen automatically. Data sits in the database between syncs. This is normal and correct for a farming advisory app: weather forecasts update a few times a day at most upstream, NASA POWER's own history has a 2-3 day satellite-processing lag by design, and a farmer checking conditions doesn't need millisecond freshness — they need today's number to be genuinely today's number, which it is once synced.

If you'd rather drive syncing from an external scheduler instead of the built-in one (e.g. a multi-worker gunicorn deployment, where you'd set `SCHEDULER_AUTOSTART=False` on every worker to avoid duplicate runs), `python manage.py sync_weather` still works standalone and logs to the same `SchedulerLog` table:
```bash
# crontab -e
0 6,12,18 * * * cd /path/to/backend && venv/bin/python manage.py sync_weather
```
This also regenerates the forecast-driven alerts (heavy rain tomorrow, dry spells, heatwaves, high wind, high UV) each time it runs, deduplicated so re-running doesn't spam the same alert twice — see section 3a below.

So: real data, real APIs, an automatic hourly sync with no manual intervention, plus a real on-demand refresh path — just not a permanently-open live stream, which wouldn't actually be useful for this kind of app anyway.

## 1. Backend setup (Django)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_data --reset      # imports the Excel file + seeds all reference data
python manage.py train_ml_models        # trains the disease/irrigation/yield ML models
python manage.py createsuperuser        # optional, for /admin/

python manage.py runserver 0.0.0.0:8000
```

Optionally, also pull live weather (see section 3a below) instead of the seeded sample data:
```bash
python manage.py sync_weather
```

The API is now live at `http://127.0.0.1:8000/api/`. The Django admin (full CRUD over every table) is at `http://127.0.0.1:8000/admin/`.

A pre-seeded `db.sqlite3` ships with this project so it works out of the box; it includes a default superuser:

```
username: admin
password: agriaura123
```

Change this password (or delete `db.sqlite3` and re-run `migrate` + `seed_data` + `createsuperuser`) before deploying anywhere beyond your own machine.

### Live weather data: NASA POWER + Open-Meteo

By default the project ships with synthetic weather data (from `seed_data`) so it works immediately without any external dependency. To pull **real** weather:

```bash
python manage.py sync_weather              # all farms
python manage.py sync_weather --farm 1      # a specific farm
python manage.py sync_weather --history-days 7 --forecast-days 7
```

This calls two free, no-API-key-required sources, each used for what it's actually good at, and each written to its own database table:

| Source | Used for | Stored in | Why |
|---|---|---|---|
| **NASA POWER** (`power.larc.nasa.gov`) | Recent history | `ActualWeatherReading` — the Actual Weather Database | Satellite/reanalysis-derived, but lags ~2-3 days behind real time — not suitable for "today" or future dates. |
| **Open-Meteo** (`api.open-meteo.com`) | Today + 7-day forecast | `ForecastWeatherReading` — the Forecast Weather Database | Live numerical weather model output, no API key, free up to 10,000 calls/day. |

**Actual and forecast weather live in separate tables, not one table with a flag.** `ActualWeatherReading` never contains a predicted value — there's no field to check, because a row's presence in that table *is* the guarantee. `ForecastWeatherReading` additionally carries `confidence_score` (0-1, decaying with lead time — tomorrow's forecast is more reliable than day 7's) and `prediction_model` (which upstream model produced it), neither of which makes sense on an actual reading. Query them separately via `GET /api/weather/actual/` and `GET /api/weather/forecast/`.

Both APIs return only raw meteorological variables (temperature, humidity, rainfall, solar radiation, wind, and now also UV index, wind direction/gusts, precipitation probability, and sunrise/sunset — all free in the same daily payload, just unused in the original build). Per AgriAura's established architecture, **ET₀, VPD, and GDD are always computed deterministically** from those raw values in `advisory/weather_service.py` — never fetched externally and never ML-estimated:

- **VPD** — Tetens saturation vapour pressure equation
- **ET₀** — simplified Hargreaves-Samani equation, using the measured solar radiation from either source
- **GDD** — standard growing-degree-days (mean temp − base temp, floored at 0), accumulated against the farm's `base_temp_c`
- **Feels-like temperature** — a simple heat-index adjustment for high humidity + high temp, exposed as `feels_like_c`

`sync_weather` is idempotent (`update_or_create` keyed on farm + date) and chains GDD cumulative totals onto whatever's already in the database, so re-running it doesn't reset progress. Forecast rows are fully replaced each run (since forecasts change as the model updates); history rows are only added/updated, never deleted.

**This now runs automatically** — you don't need to schedule anything yourself. `advisory/scheduler.py` starts an APScheduler background job when the Django server starts (see "Is this actually real-time?" above for details, config env vars, and the external-cron fallback for multi-worker deployments).

There's also an on-demand path for the frontend's "Refresh Now" button: `POST /api/weather/refresh/?farm=1` runs a sync synchronously inside the request and returns the freshly updated `today_weather`, so a user can pull live data without waiting for the next scheduled run. For triggering a full all-farms sync out of band, use `POST /api/scheduler/run-now/` (also what the dashboard's Scheduler Monitoring panel's "Run sync now" button calls).

**Note for sandboxed/restricted environments:** if your network has an egress allowlist (e.g. corporate proxy, some CI runners, some cloud sandboxes), you'll need to add `power.larc.nasa.gov` and `api.open-meteo.com` to it, or `sync_weather` will fail with a connection/403 error. The command degrades gracefully — if one source fails, it still syncs whatever the other source returned.

### 3a. Forecast-driven weather alerts

Every `sync_weather` run also evaluates six rules against the freshly-synced history and forecast, defined in `advisory/weather_service.py::generate_weather_alerts()`:

| Rule | Trigger |
|---|---|
| Heavy rain tomorrow | ≥25mm forecast for the next day |
| Dry spell | 4+ consecutive days with <2mm rainfall (looking at recent history + near forecast) |
| Heatwave | 3+ consecutive forecast days ≥38°C |
| Cold/chill risk | Forecast minimum temp more than 5°C below the farm's GDD base temperature |
| High wind / spray-drift warning | Forecast wind gusts ≥35 km/h |
| High UV | Forecast UV index ≥9 |

Each generated alert is deduplicated by a `rule_key` (e.g. `heavy_rain_2026-07-02`) so re-syncing doesn't create duplicates, and alerts that no longer apply (e.g. the rain moved, the heatwave passed) are automatically deactivated on the next sync — `Alert.source="weather_rule"` marks these as distinct from the manually-seeded sample alerts, and the frontend shows a pulsing **LIVE** tag on them. Skip alert generation with `python manage.py sync_weather --no-alerts` if you only want the raw data synced.

### Re-importing the Excel file

`seed_data` reads `backend/advisory/data/pest_disease.xlsx`. To refresh from a new copy of the spreadsheet, replace that file and re-run:

```bash
python manage.py seed_data --reset
```

The command is idempotent — `--reset` clears existing rows first; without it, records are matched and updated by their natural key (`sr_no` for diseases/irrigation rules).

### Key API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/dashboard/?farm=1` | Composite payload powering the dashboard home page in one request |
| `GET /api/diseases/?ordering=-risk_score` | All 30 diseases/pests, lightweight list |
| `GET /api/diseases/<id>/` | Full disease detail incl. treatment protocol |
| `GET /api/irrigation-rules/` | All 10 soil-type/stage irrigation rules |
| `GET /api/weather/actual/?farm=1&days=7` | Actual Weather Database — observed NASA POWER readings |
| `GET /api/weather/forecast/?farm=1&days=7` | Forecast Weather Database — Open-Meteo predictions, incl. `confidence_score` + `prediction_model` |
| `GET /api/alerts/?farm=1` | Active alerts |
| `GET /api/timeline/?farm=1` | AI advisory timeline items |
| `GET /api/farms/` | Farm profile(s) incl. growth-stage GDD thresholds |
| `GET /api/scheduler/status/` | Whether the automatic hourly sync is running, next run time, last run summary |
| `GET /api/scheduler/logs/?limit=20` | Recent sync runs (scheduled/manual/CLI), newest first |
| `POST /api/scheduler/run-now/` | Trigger an out-of-band sync of every farm immediately |

All endpoints are read-only (`ReadOnlyModelViewSet`) in this build since the dashboard is advisory/read-focused; extending to writes (e.g. logging actual irrigation events) is a matter of swapping in `ModelViewSet`.

## 2. Frontend setup (React + Vite)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The frontend reads the API base URL from `frontend/.env`:

```
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

Update this if your Django server runs on a different host/port (e.g. when deploying).

### Build for production

```bash
npm run build         # outputs to frontend/dist
npm run preview        # serve the production build locally
```

## 3. Machine Learning models

AgriAura includes three trained scikit-learn models, each acting as a **second opinion** alongside the existing deterministic logic — never replacing the closed-form agronomy equations (GDD, VPD, ET₀ stay exactly as they were). This mirrors the architecture used across other AgriAura builds: ML is reserved for genuinely uncertain decisions, not physics.

| Model | Algorithm | Predicts | Second opinion for |
|---|---|---|---|
| Disease risk classifier | RandomForestClassifier (one per disease type: fungal/bacterial/viral/phytoplasma/pest) | Outbreak-favorable probability (0-100%) | The Excel-derived `risk_score` |
| Irrigation requirement | RandomForestRegressor | Liters/plant needed | The soil-type/stage reference table |
| Yield prediction | GradientBoostingRegressor | Tonnes/hectare at harvest | The variety's baseline expected yield |

### Training

```bash
python manage.py train_ml_models
```

This trains all three models on **physically-grounded synthetic data** (see `advisory/ml/data_generation.py` for the full methodology) and saves them to `advisory/ml/trained_models/*.joblib`. Typical output:

```
Disease risk classifier (per disease_type, accuracy / ROC-AUC):
  fungal         acc=0.925  auc=0.978
  bacterial      acc=0.818  auc=0.897
  viral          acc=0.848  auc=0.925
  phytoplasma    acc=0.852  auc=0.932
  pest           acc=0.876  auc=0.941

Irrigation regressor: MAE=1.334 L/plant, R²=0.950
Yield regressor: MAE=2.046 t/ha, R²=0.961
```

**On data provenance, honestly:** AgriAura doesn't yet have a logged history of real field-confirmed outcomes (actual disease incidents, actual irrigation given vs. needed, actual measured yields) tied to weather records. Until that log exists, training data is generated from the same agronomic relationships already encoded in the Excel reference sheet and FAO-56 crop-coefficient literature — e.g. fungal risk is modeled as a Gaussian suitability function peaking at high humidity + long leaf wetness, irrigation requirement from a standard ETc-minus-effective-rainfall water balance, yield from a multiplicative GDD × disease × water-stress model. This is a standard, honest way to bootstrap an ML layer when the underlying relationships are well understood but a labeled outcomes dataset doesn't exist yet. Swapping in real field data later only requires changing `advisory/ml/data_generation.py`'s `generate_*_training_frame()` functions to load a CSV instead of sampling — the model classes, training pipeline, and API contract don't change.

### Where predictions show up

- **Disease detail modal** — side-by-side "Rule-Based" vs "ML Second Opinion" cards with a confidence score
- **Disease cards** (list + grid) — a small `🌲 ML: NN%` badge next to the deterministic risk bar
- **Irrigation page** (Expert Mode) — "Reference Table" vs "RandomForest Prediction" comparison, including the prediction's uncertainty (standard deviation across the forest's trees)
- **Farm page** — ML-predicted yield next to the variety's baseline expected yield

### ML API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/ml/status/` | Which models are currently trained and loadable |
| `GET /api/ml/irrigation/?farm=1` | Irrigation prediction using a farm's live weather |
| `GET /api/ml/irrigation/?soil_type=Sandy&crop_stage=Sprouting&et0_mm=5&rainfall_week_mm=10&temp_mean_c=32&humidity_pct=60&vpd_kpa=1.5` | Irrigation prediction from explicit parameters (for "what-if" scenarios) |
| `GET /api/ml/yield/?farm=1` | Yield prediction using a farm's current GDD/disease/irrigation context |
| `GET /api/ml/yield/?gdd_at_harvest=4800&avg_disease_risk_pct=20&irrigation_adequacy_pct=90&soil_type=Black%20Cotton` | Yield prediction from explicit parameters |

`GET /api/diseases/?farm=1` and `GET /api/diseases/<id>/?farm=1` also include ML predictions (`ml_risk_pct` / `ml_prediction`) when a `farm` query parameter is supplied, using that farm's most recent weather reading as context. Without a `farm` parameter, these fields are simply omitted — the API never breaks if the models aren't trained yet, it just returns `null`/omits the ML fields.

If models aren't trained, the API endpoints return `503 {"detail": "... model not trained yet. Run: python manage.py train_ml_models"}` rather than erroring, and the frontend falls back to deterministic-only display.

## 4. Interactive UI features

Beyond the original dashboard's static cards and charts, this build adds:

- **Live weather hero strip** (Weather page) — current temp, feels-like, condition, sunrise/sunset, UV index, and rain probability in one glanceable card, with a working "Refresh Now" button that triggers a real NASA POWER + Open-Meteo sync and shows "Updated X minutes ago".
- **Animated weather icons** — small CSS-animated sun/cloud/rain/snow/storm icons driven by the actual Open-Meteo weather code, not static emoji.
- **Horizontal scrollable 7-day timeline** — tap any day to jump the rest of the page's context to it; shows rain probability inline.
- **Click-to-drill-down charts** — click any point on the temperature/humidity trend chart to open a popover with that day's full breakdown (temp, humidity, rain, wind, VPD, ET₀, UV, sunrise/sunset).
- **Wind direction indicator** — a rotating arrow showing actual forecast wind direction, with a plain-language spray-safety note when gusts are high.
- **Real Leaflet + OpenStreetMap map** (Farm page) — replaces the old static gradient placeholder with an actual interactive map, farm marker, and a circle sized to the farm's real area in hectares. No API key required; map tiles load from `tile.openstreetmap.org` directly in the browser, so they need normal outbound internet access (they will not load in network-restricted sandboxes/CI runners, same as the weather APIs).
- **Farmer vs Expert mode** — Farmer mode shows a single big yes/no irrigation verdict, simple fact cards, and a lighter dashboard; Expert mode reveals the full technical breakdown, reference tables, and all charts. Genuinely different rendered content per page, not just hidden/shown via CSS.
- **Forecast-driven live alerts** with a pulsing **LIVE** badge distinguishing them from manually-seeded sample alerts (see section 3a).

## 5. Architecture notes

- **Why a `risk_score` column instead of computing it live?** The original prototype hard-coded a risk percentage per disease. This build keeps that same number as a seeded value (`DISEASE_META` in `seed_data.py`) so the UI matches the original 1:1, while leaving room to later replace it with a live rule-engine/ML calculation without touching the frontend at all (the API contract stays the same).
- **CORS**: `django-cors-headers` is configured to allow `localhost:5173` / `127.0.0.1:5173` (Vite's default) out of the box. Update `CORS_ALLOWED_ORIGINS` in `backend/config/settings.py` (or the `CORS_ALLOWED_ORIGINS` env var) for other origins.
- **i18n**: all UI strings live in `frontend/src/i18n/translations.js` under `en` / `mr` / `hi`. The `useAppSettings().t("path.to.key")` hook resolves a key, falling back to English if a translation is missing.
- **Farmer / Expert mode**: this is a real content difference, not just a label. Farmer mode shows plain-language cards (a big "water or don't water" verdict, simple soil/stage/rain facts, the advisory timeline) and hides dense charts and raw tables. Expert mode reveals the full technical layer: VPD/ETc breakdowns, the complete irrigation reference table (all 10 soil-type rules), 7-day trend charts, the disease-risk-vs-GDD scatter plot, and per-parameter weather stat pills. The toggle lives in the sidebar, persists to `localStorage`, and is read directly in each page component (`useAppSettings().mode`) rather than via CSS-only hiding, so farmer mode genuinely renders less/simpler markup instead of just hiding it.
- **Alerts on the dashboard**: active alerts now render as a compact strip at the very top of the dashboard, above the health score, so they're the first thing a farmer sees when opening the app.
- **Voice guidance**: uses the browser's native `SpeechSynthesis` API, building the narration string from live dashboard data (health score, top disease risks, today's weather, active alert count) rather than a hard-coded script.
- **Stable farm IDs across resets**: `seed_data --reset` resets the database's auto-increment sequence after clearing rows, so the farm (and every other seeded row) always comes back as id=1 on a fresh seed. Without this, SQLite's internal counter keeps climbing across repeated `--reset` runs, silently breaking anything that assumes `farm=1` (including this project's own frontend, which defaults to it).

## 6. Database schema (advisory app)

| Model | Purpose |
|---|---|
| `Disease` | One row per pest/disease from the Excel sheet (30 rows) |
| `Treatment` | Treatment protocol shared by `disease_type` (fungal/bacterial/viral/phytoplasma/pest) |
| `IrrigationRule` | Soil type × crop stage irrigation decision table (10 rows) |
| `FarmProfile` | Static farm metadata (location, variety, soil, base temp, etc.) |
| `WeatherReading` | Daily weather/agronomy readings per farm, flagged `is_forecast`. Includes UV index, wind direction/gusts, precipitation probability, sunrise/sunset, `data_source` (nasa_power/open_meteo/seed), and `fetched_at` for freshness display. |
| `Alert` | Advisory alerts per farm; `source` distinguishes manually-seeded (`manual`) from forecast-rule-generated (`weather_rule`) alerts, deduplicated by `rule_key` |
| `AdvisoryTimelineItem` | Ordered "what to do next" timeline entries |
| `CropGrowthStage` | GDD thresholds defining growth stages (Sprouting → Harvest Ready) |

## 7. Running both together

Open two terminals:

```bash
# Terminal 1
cd backend && source venv/bin/activate && python manage.py runserver 0.0.0.0:8000

# Terminal 2
cd frontend && npm run dev
```

Visit `http://localhost:5173`.
