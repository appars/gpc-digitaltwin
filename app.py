#!/usr/bin/env python3
import os, time, math, json, random, logging, threading
from dataclasses import dataclass, asdict
from typing import Dict
from flask import Flask, render_template, redirect, url_for, send_from_directory, request, jsonify
from flask_socketio import SocketIO

# ------------ logging ------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.WARNING),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

# ------------ app ------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "wgc-demo")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# ------------ domain model ------------
@dataclass
class Oper:
    T1: float = 303.15
    T2: float = 353.15
    P1: float = 3.0
    P2: float = 8.8
    flow: float = 25.0
    speed: float = 7800.0
    valve: float = 65.0

@dataclass
class Health:
    v_ax: float = 2.2
    v_vert: float = 2.8
    v_horz: float = 2.5
    oil_pressure: float = 3.2
    bearing_temp: float = 344.0
    oil_temp: float = 325.0
    seal_leak: float = 0.12

state_lock = threading.RLock()
state_oper = Oper()
state_health = Health()
setpoints: Dict[str, float] = {"speed": 7800.0, "valve": 65.0}

running_evt = threading.Event()
sim_thread: threading.Thread | None = None

def snapshot() -> dict:
    with state_lock:
        return {"oper": asdict(state_oper), "health": asdict(state_health)}

# ------------ simulation ------------
def _clip(v, lo, hi): return max(lo, min(hi, v))

def sim_step():
    global state_oper, state_health
    with state_lock:
        # follow setpoints
        state_oper.speed += (setpoints["speed"] - state_oper.speed) * 0.12
        state_oper.valve += (setpoints["valve"] - state_oper.valve) * 0.18

        # flow ~ speed and valve
        target_flow = 0.0025 * state_oper.speed + 0.18 * (state_oper.valve / 100.0) * 30.0
        state_oper.flow += (target_flow - state_oper.flow) * 0.15 + random.uniform(-0.15, 0.15)
        state_oper.flow = _clip(state_oper.flow, 20.0, 42.0)

        # pressures
        base_p1 = 3.0 + 0.05 * math.sin(time.time() * 0.15)
        dP = 0.006 * state_oper.speed + 0.04 * (state_oper.valve / 100.0) * 30.0 - 1.5
        state_oper.P1 = base_p1 + random.uniform(-0.05, 0.05)
        state_oper.P2 = _clip(state_oper.P1 + dP, 6.5, 11.5)

        # temps
        state_oper.T1 = 303.0 + random.uniform(-0.5, 0.5)
        state_oper.T2 = 352.0 + 0.02 * (state_oper.P2 - state_oper.P1) * 100 + random.uniform(-0.7, 0.7)

        # health (simple coupling)
        base_vib = 1.8 + 0.00012 * state_oper.speed + 0.04 * max(0.0, (state_oper.P2 - state_oper.P1) - 5.0)
        state_health.v_ax   = _clip(base_vib + random.uniform(-0.4, 0.4), 0.6, 8.5)
        state_health.v_vert = _clip(base_vib + random.uniform(-0.3, 0.5), 0.6, 8.5)
        state_health.v_horz = _clip(base_vib + random.uniform(-0.3, 0.4), 0.6, 8.5)

        state_health.oil_pressure = _clip(3.1 + 0.002 * (7800 - abs(7800 - state_oper.speed)) + random.uniform(-0.05, 0.05), 2.4, 4.5)
        state_health.bearing_temp = _clip(340.0 + 0.004 * state_oper.speed + random.uniform(-0.6, 0.8), 330.0, 385.0)
        state_health.oil_temp     = _clip(323.0 + 0.002 * state_oper.speed + random.uniform(-0.6, 0.8), 320.0, 370.0)
        state_health.seal_leak    = _clip(0.09 + 0.00003 * (state_oper.speed - 7000) + random.uniform(-0.01, 0.01), 0.0, 0.6)

def sim_loop():
    while running_evt.is_set():
        t0 = time.perf_counter()
        sim_step()
        socketio.emit("wgc_data", {"wgc": snapshot(), "running": running_evt.is_set()})
        time.sleep(max(0.0, 1.0 - (time.perf_counter() - t0)))

def start_sim():
    global sim_thread
    if running_evt.is_set():
        return
    running_evt.set()
    sim_thread = threading.Thread(target=sim_loop, name="wgc-sim", daemon=True)
    sim_thread.start()

def stop_sim():
    running_evt.clear()

# ------------ routes ------------
@app.route("/")
def index():
    return redirect(url_for("wgc_page"))

@app.route("/wgc")
def wgc_page():
    return render_template("wgc.html", wgc=snapshot())

@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.svg", mimetype="image/svg+xml")

# optional HTTP ingest
@app.route("/ingest-wgc", methods=["POST"])
def ingest_wgc():
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"ok": False, "error": "invalid json"}), 400
    data = payload.get("wgc", payload)
    oper = data.get("oper", {})
    health = data.get("health", {})
    with state_lock:
        for k, v in oper.items():
            if hasattr(state_oper, k):
                setattr(state_oper, k, float(v))
        for k, v in health.items():
            if hasattr(state_health, k):
                setattr(state_health, k, float(v))
    socketio.emit("wgc_data", {"wgc": snapshot(), "running": running_evt.is_set()})
    return jsonify({"ok": True})

# change log level via curl
@app.route("/admin/log-level", methods=["POST"])
def admin_log_level():
    level = (request.values.get("level") or (request.json or {}).get("level", "")).upper()
    if level in ("DEBUG","INFO","WARNING","ERROR","CRITICAL"):
        logging.getLogger().setLevel(getattr(logging, level))
        for name in logging.root.manager.loggerDict:
            logging.getLogger(name).setLevel(getattr(logging, level))
        return jsonify({"ok": True, "level": level})
    return jsonify({"ok": False, "error": "invalid level"}), 400

# ------------ socket.io ------------
@socketio.on("connect")
def on_connect():
    sid = request.sid
    socketio.emit("wgc_data", {"wgc": snapshot(), "running": running_evt.is_set()}, to=sid)

@socketio.on("wgc_command")
def on_wgc_command(message):
    action = (message or {}).get("action")
    if action == "start":
        start_sim()
    elif action == "stop":
        stop_sim()
    elif action == "setpoints":
        spd = message.get("speed")
        vlv = message.get("valve")
        with state_lock:
            if spd is not None: setpoints["speed"] = float(spd)
            if vlv is not None: setpoints["valve"] = float(vlv)
    socketio.emit("wgc_ack", {"ok": True, "action": action, "running": running_evt.is_set()}, to=request.sid)

# ------------ main ------------
if __name__ == "__main__":
    if os.getenv("WGC_AUTOSTART", "1") != "0":
        start_sim()
    socketio.run(app, host=os.getenv("HOST","0.0.0.0"), port=int(os.getenv("PORT","5050")), debug=False)

