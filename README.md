# Samsung Galaxy Watch 7 — Grafana Health Dashboard

Visualise every health metric collected by your **Samsung Galaxy Watch 7** in a self-hosted [Grafana](https://grafana.com/) dashboard backed by [InfluxDB](https://www.influxdata.com/).

## Metrics displayed

| Panel | Measurement | Fields |
|-------|-------------|--------|
| ❤️ Heart Rate | `heart_rate` | BPM (gauge + time-series, min/max/avg) |
| 🚶 Steps | `steps` | Hourly step count (bar chart + daily total) |
| 🔥 Calories | `calories` | kcal burned today |
| 📏 Distance | `distance` | km walked today |
| 🩸 SpO2 | `spo2` | Blood-oxygen % (gauge + trend) |
| 😰 Stress | `stress` | Stress score 0–100 (gauge + trend) |
| 😴 Sleep | `sleep` | Duration (min) + sleep score |
| 😴 Sleep stages | `sleep_stage` | Deep / Light / REM / Awake breakdown |
| ⚖️ Body composition | `body_composition` | Weight, body-fat %, muscle-mass %, BMI |

---

## Architecture

```
Samsung Galaxy Watch 7
        │
        │  (1) Samsung Health app export  ──▶  ingest_samsung_health.py  ──▶ InfluxDB
        │  (2) Real-time REST push         ──▶  samsung_health_api.py    ──▶ InfluxDB
                                                                                │
                                                                           Grafana
                                                                     (pre-built dashboard)
```

---

## Quick start

### Prerequisites

* [Docker](https://docs.docker.com/get-docker/) ≥ 24 and Docker Compose ≥ 2
* Python ≥ 3.10 (only needed for the ingestion scripts)

### 1 — Clone and configure

```bash
git clone https://github.com/WICHARIT10459/Grafana-dashborad.git
cd Grafana-dashborad

# Copy the example environment file and edit as needed
cp .env.example .env
```

The defaults in `.env.example` work out of the box for a local setup. Change
`INFLUXDB_TOKEN` and the Grafana admin password before exposing the stack to
the internet.

### 2 — Start the stack

```bash
docker compose up -d
```

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3000  (admin / admin) |
| InfluxDB | http://localhost:8086  (admin / adminpassword) |

The dashboard **Samsung Galaxy Watch 7 — Health Dashboard** is auto-provisioned
at startup. No manual import required.

---

## Sending data to InfluxDB

### Option A — Import a Samsung Health export (recommended first step)

1. Open the **Samsung Health** app on your phone.
2. Tap the three-dot menu → **Settings** → **Download personal data**.
3. Extract the downloaded ZIP to a local folder.
4. Run the importer:

```bash
# Install Python dependencies (one-time)
pip install -r ingestion/requirements.txt

# Import all CSV files from the export folder
python ingestion/ingest_samsung_health.py \
    --input-dir /path/to/samsung_health_export \
    --url http://localhost:8086 \
    --token my-super-secret-token \
    --org samsung_health \
    --bucket galaxy_watch
```

Supported file names (matched by keyword):

| Keyword in filename | Measurement written |
|---------------------|---------------------|
| `heart_rate` | `heart_rate` |
| `step_count` / `pedometer` | `steps` |
| `calories` | `calories` |
| `sleep_stage` | `sleep_stage` |
| `sleep` | `sleep` |
| `blood_oxygen` | `spo2` |
| `stress` | `stress` |
| `body` | `body_composition` |

> **Tip:** use `--dry-run` to test parsing without writing anything to InfluxDB.

---

### Option B — Real-time push via REST API

Start the ingestion API (connects to InfluxDB specified in your `.env`):

```bash
pip install -r ingestion/requirements.txt
python ingestion/samsung_health_api.py --port 5000
```

Then push measurements from any HTTP client (e.g. a custom Galaxy Watch app,
Tasker, or a cron job reading Samsung Health data):

```bash
# Heart rate
curl -X POST http://localhost:5000/api/v1/heart_rate \
     -H "Content-Type: application/json" \
     -d '{"bpm": 72, "timestamp": "2024-01-15T10:30:00Z"}'

# Steps
curl -X POST http://localhost:5000/api/v1/steps \
     -d '{"count": 120, "kcal": 5.2, "distance_m": 90.0,
          "timestamp": "2024-01-15T10:30:00Z"}'

# Blood oxygen
curl -X POST http://localhost:5000/api/v1/spo2 \
     -d '{"percent": 98.0, "timestamp": "2024-01-15T10:30:00Z"}'

# Stress
curl -X POST http://localhost:5000/api/v1/stress \
     -d '{"score": 35, "timestamp": "2024-01-15T10:30:00Z"}'

# Sleep session
curl -X POST http://localhost:5000/api/v1/sleep \
     -d '{"duration_minutes": 450, "score": 82,
          "timestamp": "2024-01-15T07:00:00Z"}'

# Sleep stage  (stage: "Awake" | "Light" | "Deep" | "REM")
curl -X POST http://localhost:5000/api/v1/sleep_stage \
     -d '{"stage": "Deep", "minutes": 25.0,
          "timestamp": "2024-01-15T02:00:00Z"}'

# Body composition
curl -X POST http://localhost:5000/api/v1/body_composition \
     -d '{"weight_kg": 70.5, "body_fat_percent": 18.2,
          "muscle_mass_percent": 38.5, "bmi": 22.1,
          "timestamp": "2024-01-15T08:00:00Z"}'

# Batch — multiple measurements in one request
curl -X POST http://localhost:5000/api/v1/batch \
     -d '[{"measurement":"heart_rate","bpm":72},
          {"measurement":"spo2","percent":98}]'

# Liveness check
curl http://localhost:5000/health
```

---

## Project structure

```
.
├── docker-compose.yml                  # InfluxDB + Grafana stack
├── .env.example                        # Environment variables template
├── ingestion/
│   ├── requirements.txt                # Python dependencies
│   ├── ingest_samsung_health.py        # Samsung Health CSV importer
│   └── samsung_health_api.py           # Real-time REST API
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/influxdb.yml    # Auto-provision InfluxDB datasource
│   │   └── dashboards/dashboards.yml   # Auto-provision dashboard folder
│   └── dashboards/
│       └── samsung_watch_health.json   # Pre-built Grafana dashboard
└── tests/
    └── test_ingestion.py               # Unit tests (44 tests)
```

---

## Development

```bash
# Install dependencies
pip install -r ingestion/requirements.txt pytest

# Run tests
python -m pytest tests/ -v
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INFLUXDB_URL` | `http://influxdb:8086` | InfluxDB endpoint (inside Docker: use service name) |
| `INFLUXDB_TOKEN` | `my-super-secret-token` | InfluxDB API token |
| `INFLUXDB_ORG` | `samsung_health` | InfluxDB organisation |
| `INFLUXDB_BUCKET` | `galaxy_watch` | InfluxDB bucket |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |
| `API_PORT` | `5000` | Port for the real-time ingestion API |
