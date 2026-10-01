import axios from "axios";

// In development: VITE_API_BASE_URL is "/api" and Vite's proxy forwards it to
// Django on port 8000 — no CORS required.
// In production: point this to your server's /api path or a reverse proxy URL.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

// Append ?_t=<timestamp> to every GET request so the browser never
// serves a cached (stale) response for dashboard / weather / disease data.
api.interceptors.request.use((config) => {
  if (!config.method || config.method === "get") {
    config.params = { ...config.params, _t: Date.now() };
  }
  return config;
});

/* ===================== DASHBOARD ===================== */
export const fetchDashboard = (farmId = 1) =>
  api.get("/dashboard/", { params: { farm: farmId } }).then((r) => r.data);

/* ===================== DISEASES ===================== */
export const fetchDiseases = (params = {}) =>
  api.get("/diseases/", { params: { ordering: "-risk_score", farm: 1, ...params } }).then((r) => r.data);

export const fetchDiseaseDetail = (id, farmId = 1) =>
  api.get(`/diseases/${id}/`, { params: { farm: farmId } }).then((r) => r.data);

/* ===================== ML ===================== */
export const fetchMlStatus = () => api.get("/ml/status/").then((r) => r.data);
export const fetchIrrigationMlPrediction = (params) =>
  api.get("/ml/irrigation/", { params }).then((r) => r.data);
export const fetchYieldMlPrediction = (params) =>
  api.get("/ml/yield/", { params }).then((r) => r.data);

/* ===================== IRRIGATION ===================== */
export const fetchIrrigationRules = (params = {}) =>
  api.get("/irrigation-rules/", { params }).then((r) => r.data);

/* ===================== WEATHER ===================== */
export const fetchActualWeather = (farmId = 1, params = {}) =>
  api.get("/weather/actual/", { params: { farm: farmId, ...params } }).then((r) => r.data);

export const fetchForecastWeather = (farmId = 1, params = {}) =>
  api.get("/weather/forecast/", { params: { farm: farmId, ...params } }).then((r) => r.data);

export const refreshWeatherNow = (farmId = 1) =>
  api.post("/weather/refresh/", null, { params: { farm: farmId }, timeout: 30000 }).then((r) => r.data);

/* ===================== SCHEDULER ===================== */
export const fetchSchedulerStatus = () => api.get("/scheduler/status/").then((r) => r.data);
export const fetchSchedulerLogs = (limit = 10) =>
  api.get("/scheduler/logs/", { params: { limit } }).then((r) => r.data);
export const runSchedulerNow = () =>
  api.post("/scheduler/run-now/", null, { timeout: 30000 }).then((r) => r.data);

/* ===================== ALERTS ===================== */
export const fetchAlerts = (farmId = 1) =>
  api.get("/alerts/", { params: { farm: farmId } }).then((r) => r.data);

/* ===================== TIMELINE ===================== */
export const fetchTimeline = (farmId = 1) =>
  api.get("/timeline/", { params: { farm: farmId } }).then((r) => r.data);

/* ===================== FARM ===================== */
export const fetchFarms = () => api.get("/farms/").then((r) => r.data);
export const fetchFarm = (id) => api.get(`/farms/${id}/`).then((r) => r.data);
export const patchFarm = (id, data) => api.patch(`/farms/${id}/`, data).then((r) => r.data);
