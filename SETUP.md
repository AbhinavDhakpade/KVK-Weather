# AgriAura Setup (First Time Only)

## Backend Setup
```bash
cd backend
python -m venv venv

# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_data --reset
python manage.py createsuperuser
python manage.py train_ml_models
```

## Frontend Setup
```bash
cd frontend
npm install
```

## Run the App
- **Windows:** Double-click `START_WINDOWS.bat`
- **Mac/Linux:** Run `./START_MAC_LINUX.sh`
- Or manually: open 2 terminals and run each server separately

## Open
http://localhost:5173

## Admin Panel
http://localhost:8000/admin  →  the superuser you create with `python manage.py createsuperuser`
