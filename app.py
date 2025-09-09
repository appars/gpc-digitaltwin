import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from flask_socketio import SocketIO, emit

# ----------------- Logging: keep console clean -----------------
def _init_logging():
    # Default WARNING; change with LOG_LEVEL=INFO or DEBUG if you ever need it
    level_name = os.getenv("LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # Silence Werkzeug access logs entirely (in case anyone runs the dev server)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("werkzeug.serving").setLevel(logging.ERROR)

    # Silence python-socketio/engineio internal logs
    logging.getLogger("engineio").setLevel(logging.ERROR)
    logging.getLogger("socketio").setLevel(logging.ERROR)

_init_logging()
log = logging.getLogger("app")

# ----------------- Flask & Socket.IO -----------------
app = Flask(__name__, static_folder="static", template_folder="templates")

# Force Eventlet (quiet) and silence Socket.IO loggers
# NOTE: Ensure `pip install eventlet`
socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False
)

# ----------------- State -----------------
wgc_state = {
    "oper": {
        "T1": None, "T2": None,   # K
        "P1": None, "P2": None,   # bar
        "flow": None,             # kg/s
        "speed": None,            # rpm
        "valve": None             # %
    },
    "health": {
        "v_ax": 0.0, "v_vert": 0.0, "v_horz": 0.0,        # mm/s
        "oil_pressure": None, "bearing_temp": None,
        "oil_temp": None, "seal_leak": None
    },
    "ts": None
}
running = False  # server-side run flag

# ----------------- Routes -----------------
@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static", "favicon.svg", mimetype="image/svg+xml")

@app.route("/")
def index():
    # You can keep a simple home or redirect straight to the dashboard
    return redirect(url_for("wgc"))

@app.route("/wgc")
def wgc():
    # Bootstrap snapshot for the client
    snap = {
        "oper": wgc_state["oper"],
        "health": wgc_state["health"],
        "ts": wgc_state["ts"],
        "running": running
    }
    return render_template("wgc.html", wgc=snap)

# Telemetry ingest (quiet)
@app.post("/ingest-wgc")
def ingest_wgc():
    global wgc_state
    try:
        data = request.get_json(silent=True) or {}
        oper = data.get("oper") or {}
        health = data.get("health") or {}

        # update state
        wgc_state["oper"].update(oper)
        wgc_state["health"].update(health)
        wgc_state["ts"] = datetime.utcnow().isoformat() + "Z"

        # broadcast to all dashboards (no noisy logs)
        payload = {"wgc": {"oper": wgc_state["oper"],
                           "health": wgc_state["health"],
                           "ts": wgc_state["ts"]},
                   "running": running}
        socketio.emit("wgc_data", payload)
        return jsonify({"ok": True})
    except Exception as e:
        # Only warn on errors
        log.warning("ingest error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 400

# ----------------- WebSocket events -----------------
@socketio.on("connect")
def ws_connect():
    # Push a snapshot on connect
    emit("wgc_data", {"wgc": wgc_state, "running": running})

@socketio.on("wgc_command")
def ws_wgc_command(msg):
    global running
    try:
        action = (msg or {}).get("action")
        if action == "start":
            running = True
        elif action == "stop":
            running = False
        elif action == "setpoints":
            spd = msg.get("speed")
            v   = msg.get("valve")
            if isinstance(spd, (int, float)):
                wgc_state["oper"]["speed"] = float(spd)
            if isinstance(v, (int, float)):
                wgc_state["oper"]["valve"] = float(v)
        # Ack back (keeps the UI badge in sync)
        emit("wgc_ack", {"ok": True, "running": running})
    except Exception as e:
        emit("wgc_ack", {"ok": False, "error": str(e)})

# ----------------- Main -----------------
if __name__ == "__main__":
    # Eventlet server (quiet): no access logs, no polling lines
    port = int(os.getenv("PORT", "5050"))
    # log_output=False keeps eventlet from printing per-request logs
    socketio.run(app, host="0.0.0.0", port=port, log_output=False)

