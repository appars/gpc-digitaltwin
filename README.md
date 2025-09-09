# Wet Gas Compressor — Digital Twin (Real‑Time Monitoring & Optimization)

This repository showcases a professional, demo-grade Digital Twin for a Wet Gas Compressor (WGC). It ingests synthetic process & mechanical-health telemetry in real time and renders an operator-friendly web dashboard for monitoring, diagnostics, and what-if control.

> **Live Demo (Cloud Run):** https://wgc-demo-502630974508.us-central1.run.app/wgc


![Dashboard](docs/screenshot.png)

---

## ⭐ What you get

- **Real‑time dashboards** (Chart.js): process (Flow/P1/P2) and vibration (Ax/Vert/Horz).
- **Dark / Light** theme toggle.
- **Zoom & Pan** on charts (local plugins included).
- **Thresholds & shading** (warn/trip bands for P2 and vibration).
- **Compressor performance map**: synthetic speed lines + surge line + current operating point.
- **Replay last window**: time scrubber, Replay / Stop Replay, Live mode.
- **Controls**: Pause/Resume/Clear charts.
- **Setpoints**: Speed & Valve sliders with *Apply* (emits command to server).
- **Start/Stop** WGC commands (sends `wgc_command` via WebSocket).
- **Exports**: PNG (per‑chart), CSV (timeseries), PDF (2‑up charts), PDF daily report (KPIs + alarms + chart).
- **Quiet server logs** out of the box (Werkzeug access logs disabled).

---

## 🧱 Architecture

- **Flask + Flask‑SocketIO** service
  - Routes: `/wgc` (dashboard), `/ingest-wgc` (data ingest, JSON), static assets under `/static`.
  - WebSocket channel pushes updates to the UI and receives commands.
- **Simulator** (`wgc_sim.py` or containerized job) posts JSON samples to `/ingest-wgc`.
- **No database** (in‑memory ring buffer + browser history only).

```
(sim) ──HTTP POST──>  /ingest-wgc  →  server keeps snapshot → emits via Socket.IO →  browser charts
```

---

## 🚀 Run locally

### 1) Clone & install

```bash
git clone https://github.com/appars/gpc-digitaltwin.git
cd gpc-digitaltwin

# (optional) use a virtualenv
python3 -m venv venv && source venv/bin/activate

pip install -r requirements.txt
```

### 2) Start the app

```bash
python app.py
# Serves on http://127.0.0.1:5050  (and LAN IP)
```

Open: **http://localhost:5050/wgc**

### 3) Start the simulator (local)

```bash
python wgc_sim.py --url http://localhost:5050 --hz 1.0 --log-every 60 --verbose
```

**Simulator options**

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `--url` | `TWIN_URL` | `http://localhost:5050` | Base URL of the Flask service |
| `--hz` | `SIM_HZ` | `1.0` | Samples per second |
| `--log-every` | `SIM_LOG_EVERY` | `0` | Log every N samples (0 = silent) |
| `--verbose` | `SIM_VERBOSE=1` | off | Log network errors & status |
| *(n/a)* | `SIM_TIMEOUT` | `3.0` | POST timeout (seconds) |

> You can also just set env vars and run `python wgc_sim.py` with no flags.

---

## ☁️ Deploy on Google Cloud Run (App)

**Prereqs**: A GCP project, Artifact Registry repo (or use Cloud Build default), `gcloud` CLI, billing enabled.

1. **Build & deploy** (from repo root, Cloud Shell is easiest):

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION=us-central1
SERVICE=wgc-demo

gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/wgc/$SERVICE:latest

gcloud run deploy $SERVICE   --image $REGION-docker.pkg.dev/$PROJECT_ID/wgc/$SERVICE:latest   --region $REGION   --allow-unauthenticated   --port 5050
```

2. **Open** the URL printed by `gcloud run deploy` and append `/wgc`

> Example: `https://wgc-demo-XXXXXXXXXXX.us-central1.run.app/wgc`

> The service is **stateless** and **keeps data in memory** only.

---

## 🏃 Run the simulator on Cloud Run Jobs

You can push synthetic data from the cloud instead of your laptop.

### 1) Build & push the sim image

```bash
# one-time layout
mkdir -p sim
cp Dockerfile.sim sim/Dockerfile
cp wgc_sim.py sim/

PROJECT_ID=$(gcloud config get-value project)
REGION=us-central1
REPO=wgc
IMAGE=wgc-sim

gcloud builds submit sim --tag $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:latest
```

### 2) Create the Job (gen2 requires ≥ 1 vCPU and ≥ 512Mi)

```bash
JOB=wgc-sim
SERVICE_URL="https://wgc-demo-502630974508.us-central1.run.app"

gcloud run jobs create $JOB   --image $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE:latest   --region $REGION   --set-env-vars TWIN_URL=$SERVICE_URL,SIM_HZ=1.0,SIM_LOG_EVERY=60,SIM_VERBOSE=1   --cpu=1 --memory=512Mi   --task-timeout=86400s   --max-retries=0
```

> If the job already exists, use `gcloud run jobs update …` with the same flags.

### 3) Execute / Stop

```bash
gcloud run jobs execute $JOB --region $REGION
# To stop, delete the execution (or let it exit if your sim exits)
gcloud run jobs executions list --region $REGION --job $JOB
gcloud run jobs executions delete EXECUTION_ID --region $REGION
```

### 4) Tail logs

```bash
REGION=us-central1
JOB=wgc-sim

gcloud beta logging tail   --log-filter='resource.type="run_job"
                AND resource.labels.location="'$REGION'"
                AND resource.labels.job_name="'$JOB'"'   --format='table(timestamp,severity,textPayload,jsonPayload.message)'
```

---

## 🔧 Server configuration

The Flask service reads a few environment variables:

| Env | Default | Purpose |
|---|---|---|
| `PORT` | `5050` | Listening port (Cloud Run sets this automatically) |
| `WGC_LOG_REQUESTS` | `0` | If `1`, enable Werkzeug access logs; default is silent |
| `WGC_LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`) |

**Endpoints**

- `GET /wgc` — dashboard UI
- `POST /ingest-wgc` — ingest JSON payload `{{oper:{...}, health:{...}}}`
- WebSocket (Socket.IO) — real‑time updates + `wgc_command` (start/stop/setpoints)

**Expected payload** (example)
```json
{
  "oper": {"T1":303.2,"T2":352.8,"P1":3.02,"P2":8.82,"flow":26.1,"speed":7811,"valve":65},
  "health": {"v_ax":2.6,"v_vert":2.9,"v_horz":3.1,"oil_pressure":3.6,"bearing_temp":340,"oil_temp":335,"seal_leak":0.2}
}
```

---

## 📁 Project layout

```
.
├─ app.py
├─ wgc_sim.py
├─ requirements.txt
├─ templates/
│  └─ wgc.html          # UI (Chart.js + Socket.IO)
├─ static/
│  ├─ favicon.svg
│  └─ vendor/
│     ├─ chartjs-plugin-zoom.umd.min.js
│     └─ chartjs-plugin-annotation.umd.min.js
├─ Dockerfile           # app container
├─ Dockerfile.sim       # simulator container
├─ sim/                 # (optional) build context for the job
├─ docs/
│  └─ screenshot.png    # add your screenshot
└─ README.md
```

---

## 🧪 Local tips

- If **charts are blank**:
  - Make sure the **simulator** is posting to your app URL.
  - Check browser console for plugin loading — both plugins are served locally from `/static/vendor/`.
- If using **Cloud Run**, ensure the **simulator points to the Cloud Run URL** and your service allows **unauthenticated** access (for the UI) while ingest is open to POSTs.
- Socket.IO on Cloud Run works over **WebSockets** and **polling**; no extra config needed.

---
## 📜 License

```
MIT © 2025 Apparsamy Perumal

---

## 🙌 Acknowledgments

- Charting with **Chart.js** (+ zoom & annotation plugins)
- PDFs with **jsPDF**
- WebSockets with **Flask‑SocketIO**
