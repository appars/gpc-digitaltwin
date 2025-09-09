import os, io, csv, logging
from datetime import datetime
from collections import deque
from flask import Flask, render_template, redirect, url_for, request, jsonify, Response, send_from_directory
from flask_socketio import SocketIO

# ── Quiet logging (WARNING by default) ─────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()  # DEBUG/INFO/WARNING/ERROR/CRITICAL
LEVELS = {n: getattr(logging, n) for n in ("DEBUG","INFO","WARNING","ERROR","CRITICAL")}
logging.basicConfig(level=LEVELS.get(LOG_LEVEL, logging.WARNING), format="%(message)s")
for name in ("engineio", "socketio", "werkzeug"):
    logging.getLogger(name).setLevel(logging.ERROR)

# ── App / Socket.IO ───────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                    logger=False, engineio_logger=False)

def dlog(msg, *a):
    if app.logger.isEnabledFor(logging.DEBUG):
        app.logger.debug(msg, *a)

# ── State ─────────────────────────────────────────────────────────────────────
wgc_state = {
    "running": True,
    "gas": {"mw": 18.0, "glr": 1000.0, "water_ppm": 50,
            "composition": {"CH4":0.80,"C2H6":0.07,"C3H8":0.04,"CO2":0.05,"H2S":0.01,"H2O":0.03}},
    "oper": {"T1":300.0,"T2":360.0,"P1":3.0,"P2":9.0,"flow":25.0,"speed":7800.0,"valve":65.0},
    "health": {"vib_axial":2.2,"vib_vert":2.8,"vib_horz":2.5,
               "bearing_temp":345.0,"oil_temp":325.0,"lube_oil_pressure":3.2,"seal_leakage":0.12},
    "kpi": {}
}
wgc_history = deque(maxlen=2000)

# ── KPIs ──────────────────────────────────────────────────────────────────────
def compute_wgc_kpis(st):
    oper, gas, h = st.get("oper", {}), st.get("gas", {}), st.get("health", {})
    P1, P2 = float(oper.get("P1", 1.0)), float(oper.get("P2", 1.0))
    T1, T2 = float(oper.get("T1", 300.0)), float(oper.get("T2", 350.0))
    flow, speed = float(oper.get("flow", 10.0)), float(oper.get("speed", 6000.0))
    mw = float(gas.get("mw", 18.0))

    cr = P2 / max(P1, 1e-6)
    n = 1.3
    R = 8.314 / (mw / 1000.0)
    head_idx = (n/(n-1.0)) * R * T1 * (cr ** ((n-1.0)/n) - 1.0)
    head_norm = head_idx / 50000.0
    surge_flow = max(0.2 * speed / 1000.0 + 10.0, 1e-3)
    sm_pct = ((flow - surge_flow) / surge_flow) * 100.0
    dT = max(T2 - T1, 1e-3)
    eff_idx = max(0.0, min(100.0, 80.0 - 0.15 * dT + 5.0 * (1.0 / cr)))

    def band(v): return "OK" if v < 3.5 else ("Warning" if v < 7.1 else "Trip")
    vib = {ax: {"value": float(h.get(k, 0.0)), "band": band(float(h.get(k, 0.0)))}
           for ax, k in (("axial","vib_axial"),("vertical","vib_vert"),("horizontal","vib_horz"))}

    alarms = []
    if sm_pct < 10.0: alarms.append({"type":"Surge","message":"Low surge margin","severity":"Warn" if sm_pct>0 else "Trip"})
    if any(v["band"]=="Trip" for v in vib.values()): alarms.append({"type":"Vibration","message":"High vibration","severity":"Trip"})
    elif any(v["band"]=="Warning" for v in vib.values()): alarms.append({"type":"Vibration","message":"Vibration caution","severity":"Warn"})
    if float(h.get("lube_oil_pressure",3.0)) < 2.0: alarms.append({"type":"LubeOil","message":"Low lube oil pressure","severity":"Warn"})
    if float(h.get("bearing_temp",345.0)) > 370.0: alarms.append({"type":"Bearing","message":"High bearing temp","severity":"Warn"})
    if float(h.get("seal_leakage",0.1)) > 0.5: alarms.append({"type":"Seal","message":"Excessive seal leakage","severity":"Warn"})

    return {"compression_ratio":cr,"head_index_norm":head_norm,"surge_margin_pct":sm_pct,
            "efficiency_index":eff_idx,"vibration":vib,"alarms":alarms}

def append_history():
    oper, h, k = wgc_state["oper"], wgc_state["health"], wgc_state.get("kpi", {})
    wgc_history.append({
        "ts": datetime.utcnow().isoformat(timespec="seconds")+"Z",
        "flow": round(float(oper.get("flow",0)),3), "P1": round(float(oper.get("P1",0)),3),
        "P2": round(float(oper.get("P2",0)),3), "T1": round(float(oper.get("T1",0)),3),
        "T2": round(float(oper.get("T2",0)),3), "speed": round(float(oper.get("speed",0)),3),
        "valve": round(float(oper.get("valve",0)),3),
        "v_ax": round(float(h.get("vib_axial",0)),3), "v_v": round(float(h.get("vib_vert",0)),3),
        "v_h": round(float(h.get("vib_horz",0)),3), "oil_p": round(float(h.get("lube_oil_pressure",0)),3),
        "bearingT": round(float(h.get("bearing_temp",0)),3), "oilT": round(float(h.get("oil_temp",0)),3),
        "seal": round(float(h.get("seal_leakage",0)),3),
        "cr": round(float(k.get("compression_ratio",0)),4),
        "sm_pct": round(float(k.get("surge_margin_pct",0)),4),
        "head_norm": round(float(k.get("head_index_norm",0)),6),
        "eff_idx": round(float(k.get("efficiency_index",0)),3)
    })

# ── Responses / routes ────────────────────────────────────────────────────────
@app.after_request
def cache_headers(resp):
    if request.path.endswith("favicon.svg"):
        resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
    return resp

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.svg", mimetype="image/svg+xml")

@app.route("/")
def index():
    return redirect(url_for("wgc_index"))

@app.route("/wgc")
def wgc_index():
    dlog("[HTTP] render /wgc")
    return render_template("wgc.html", wgc=wgc_state)

# Admin: log level via curl
@app.get("/admin/log-level")
def get_log_level():
    return {"level": logging.getLevelName(logging.getLogger().level)}

@app.post("/admin/log-level")
def post_log_level():
    payload = request.get_json(silent=True) or {}
    level = str(payload.get("level", "")).upper()
    if level not in LEVELS:  # invalid
        return jsonify({"ok": False, "error": "invalid level", "allowed": list(LEVELS)}), 400
    logging.getLogger().setLevel(LEVELS[level])
    app.logger.setLevel(LEVELS[level])
    # keep lib logs quiet unless DEBUG
    for name in ("engineio","socketio","werkzeug"):
        logging.getLogger(name).setLevel(logging.INFO if level=="DEBUG" else logging.ERROR)
    return {"ok": True, "level": level}

# API for snapshot/history/ingest
@app.route("/api/wgc/snapshot")
def wgc_snapshot():
    return jsonify(wgc_state)

@app.route("/api/wgc/history.csv")
def wgc_history_csv():
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["timestamp","flow","P1","P2","T1","T2","speed","valve",
                "vib_axial","vib_vert","vib_horz","lube_oil_pressure","bearing_temp","oil_temp","seal_leakage",
                "compression_ratio","surge_margin_pct","head_index_norm","efficiency_index"])
    for r in wgc_history:
        w.writerow([r["ts"], r["flow"], r["P1"], r["P2"], r["T1"], r["T2"], r["speed"], r["valve"],
                    r["v_ax"], r["v_v"], r["v_h"], r["oil_p"], r["bearingT"], r["oilT"], r["seal"],
                    r["cr"], r["sm_pct"], r["head_norm"], r["eff_idx"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=wgc_history.csv"})

@app.route("/api/wgc/clear", methods=["POST"])
def wgc_history_clear():
    wgc_history.clear()
    return {"ok": True}

@app.route("/api/wgc/ingest", methods=["POST"])
def wgc_ingest():
    data = request.get_json(silent=True) or {}
    dlog("[HTTP] ingest keys=%s", list(data.keys()))
    for section in ("gas","oper","health"):
        if section in data:
            wgc_state.setdefault(section, {}).update(data[section])
    wgc_state["kpi"] = compute_wgc_kpis(wgc_state)
    append_history()
    socketio.emit("update_wgc", wgc_state)
    return jsonify({"ok": True})

# ── Sockets ───────────────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    dlog("[WS] dashboard connected")
    socketio.emit("update_wgc", wgc_state)

@socketio.on("wgc_data")
def wgc_data(data):
    dlog("[WS] wgc_data keys=%s", list(data.keys()))
    for section in ("gas","oper","health"):
        if section in data:
            wgc_state.setdefault(section, {}).update(data[section])
    wgc_state["kpi"] = compute_wgc_kpis(wgc_state)
    append_history()
    socketio.emit("update_wgc", wgc_state)

@socketio.on("wgc_command")
def wgc_command(data):
    action = (data or {}).get("action")
    dlog("[WS] wgc_command %s", action)
    if action in ("start","stop"):
        wgc_state["running"] = (action == "start")
        socketio.emit("wgc_command", {"action": action})
    if action == "set":
        sp = {k:v for k,v in (data or {}).items() if k in ("speed","valve") and v is not None}
        if sp:
            wgc_state["oper"].update(sp)
            socketio.emit("wgc_command", {"action":"set", **sp})
    socketio.emit("update_wgc", wgc_state)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5050, debug=False, use_reloader=False)

