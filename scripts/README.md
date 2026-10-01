# ThermalIntel Automation Scripts

- `setup.sh`: One-click environment bootstrapping. Installs python virtual environment, dependencies for API and Intelligence, Next.js node modules, and seeds the SQLite database.
- `dev.sh`: Launches both the FastAPI backend (`http://localhost:8000`) and the Next.js frontend (`http://localhost:3000`) in concurrent development mode.
- `seed_data.py`: Populates or resets the SQLite database (`thermalintel.db`) from `data/sample/sample_hotspots.json`, `data/sample/sample_incidents.json`, and `data/sample/sample_alerts.json`.
