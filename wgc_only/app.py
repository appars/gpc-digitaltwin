
from collections import deque
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, Response, request
from flask_socketio import SocketIO
import csv
import io

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# --------- WGC STATE + HISTORY ---------
wgc_state = {
    "running": True,
    "gas": {
        "mw": 18.0,
        "glr": 1000.0,
        "water_ppm": 50,
        "composition": {"CH4": 0.8, "C2H6": 0.07, "C3H8": 0.04, "CO2": 0.05, "H2S": 0.01, "H2O": 0.03},
    },
    "oper": {
        "T1": 300.0, "T2": 360.0,     # K
        "P1": 3.0, "P2": 9.0,         # bar abs
        "flow": 25.0,                 # kg/s
        "speed": 7800.0,              # rpm
        "valve": 65.0                 # % open
    },
    "health": {
        "vib_axial": 2.0, "vib_vert": 2.5, "vib_horz": 2.2,  # mm/s RMS
        "bearing_temp": 345.0,                               # K
        "oil_temp": 325.0,                                   # K
        "lube_oil_pressure": 3.2,                            # bar
        "seal_leakage": 0.1                                  # L/min
    },
    "kpi": {}
}

WGC_HISTORY_MAX = 2000
wgc_history = deque(maxlen=WGC_HISTORY_MAX)

def compute_wgc_kpis(state):
    oper = state.get("oper", {})
    gas = state.get("gas", {})
    health = state.get("health", {})

    P1 = float(oper.get("P1", 1.0))
    P2 = float(oper.get("P2", 1.0))
    T1 = float(oper.get("T1", 300.0))
    T2 = float(oper.get("T2", 350.0))
    flow = float(oper.get("flow", 10.0))
    speed = float(oper.get("speed", 6000.0))
    valve = float(oper.get("valve", 50.0))
    mw = float(gas.get("mw", 18.0))
    glr = float(gas.get("glr", 1000.0))

    # Compression ratio
    cr = P2 / max(P1, 1e-6)

    # Polytropic-ish head index (illustrative only)
    n = 1.3
    Rspec = 8.314 / (mw / 1000.0)  # J/kg-K
    head_index = (n/(n-1.0)) * Rspec * T1 * ((cr)**((n-1.0)/n) - 1.0)
    head_index_norm = head_index / 50000.0

    # Surge margin heuristic vs simple surge line
    surge_flow = max(0.2*speed/1000.0 + 10.0, 1e-3)
    sm = (flow - surge_flow) / surge_flow
    sm_pct = sm * 100.0

    # Efficiency index (demo)
    dT = max(T2 - T1, 1e-3)
    eff_idx = max(0.0, min(100.0, 80.0 - 0.15*dT + 5.0*(1.0/cr)))

    # Vibration bands
    def vib_band(v):
        if v < 3.5: return "OK"
        if v < 7.1: return "Warning"
        return "Trip"
    vib_axial = float(health.get("vib_axial", 2.0))
    vib_vert  = float(health.get("vib_vert", 2.0))
    vib_horz  = float(health.get("vib_horz", 2.0))
    vib_status = {
        "axial": {"value": vib_axial, "band": vib_band(vib_axial)},
        "vertical": {"value": vib_vert, "band": vib_band(vib_vert)},
        "horizontal": {"value": vib_horz, "band": vib_band(vib_horz)},
    }

    oil_p = float(health.get("lube_oil_pressure", 3.0))
    bearingT = float(health.get("bearing_temp", 345.0))
    oilT = float(health.get("oil_temp", 325.0))
    seal_leak = float(health.get("seal_leakage", 0.1))

    alarms = []
    if sm_pct < 10.0:
        alarms.append({"type": "Surge", "message": "Low surge margin", "severity": "Warn" if sm_pct>0 else "Trip"})
    if vib_axial>=7.1 or vib_vert>=7.1 or vib_horz>=7.1:
        alarms.append({"type": "Vibration", "message": "High vibration level", "severity": "Trip"})
    elif vib_axial>=3.5 or vib_vert>=3.5 or vib_horz>=3.5:
        alarms.append({"type": "Vibration", "message": "Vibration caution", "severity": "Warn"})
    if oil_p < 2.0:
        alarms.append({"type": "LubeOil", "message": "Low lube oil pressure", "severity": "Trip" if oil_p<1.5 else "Warn"})
    if bearingT > 370.0:
        alarms.append({"type": "Bearing", "message": "High bearing temperature", "severity": "Warn"})
    if seal_leak > 0.5:
        alarms.append({"type": "Seal", "message": "Excessive seal leakage", "severity": "Warn"})

    return {
        "compression_ratio": cr,
        "head_index_norm": head_index_norm,
        "surge_margin_pct": sm_pct,
        "efficiency_index": eff_idx,
        "vibration": vib_status,
        "alarms": alarms
    }

@app.route("/")
def home():
    return redirect(url_for("wgc"))

@app.route("/wgc")
def wgc():
    return render_template("wgc.html", wgc=wgc_state)

@app.route("/api/wgc/history.csv")
def wgc_history_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp","flow","P1","P2","T1","T2","speed","valve",
        "vib_axial","vib_vert","vib_horz","lube_oil_pressure","bearing_temp","oil_temp","seal_leakage",
        "compression_ratio","surge_margin_pct","head_index_norm","efficiency_index"
    ])
    for row in wgc_history:
        writer.writerow([
            row["ts"], row["flow"], row["P1"], row["P2"], row["T1"], row["T2"], row["speed"], row["valve"],
            row["v_ax"], row["v_v"], row["v_h"], row["oil_p"], row["bearingT"], row["oilT"], row["seal"],
            row["cr"], row["sm_pct"], row["head_norm"], row["eff_idx"]
        ])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=wgc_history.csv"})

@app.route("/api/wgc/clear", methods=["POST"])
def wgc_history_clear():
    wgc_history.clear()
    return {"ok": True, "message": "history cleared"}

@socketio.on("wgc_data")
def handle_wgc_data(data):
    for section in ("gas","oper","health"):
        if section in data:
            wgc_state.setdefault(section, {}).update(data[section])
    wgc_state["kpi"] = compute_wgc_kpis(wgc_state)
    oper, h, k = wgc_state["oper"], wgc_state["health"], wgc_state["kpi"]
    wgc_history.append({
        "ts": datetime.utcnow().isoformat(timespec="seconds")+"Z",
        "flow": round(float(oper.get("flow",0)),3),
        "P1": round(float(oper.get("P1",0)),3),
        "P2": round(float(oper.get("P2",0)),3),
        "T1": round(float(oper.get("T1",0)),3),
        "T2": round(float(oper.get("T2",0)),3),
        "speed": round(float(oper.get("speed",0)),3),
        "valve": round(float(oper.get("valve",0)),3),
        "v_ax": round(float(h.get("vib_axial",0)),3),
        "v_v": round(float(h.get("vib_vert",0)),3),
        "v_h": round(float(h.get("vib_horz",0)),3),
        "oil_p": round(float(h.get("lube_oil_pressure",0)),3),
        "bearingT": round(float(h.get("bearing_temp",0)),3),
        "oilT": round(float(h.get("oil_temp",0)),3),
        "seal": round(float(h.get("seal_leakage",0)),3),
        "cr": round(float(k.get("compression_ratio",0)),4),
        "sm_pct": round(float(k.get("surge_margin_pct",0)),4),
        "head_norm": round(float(k.get("head_index_norm",0)),6),
        "eff_idx": round(float(k.get("efficiency_index",0)),3),
    })
    socketio.emit("update_wgc", wgc_state)

@socketio.on("wgc_command")
def handle_wgc_command(data):
    action = (data or {}).get("action")
    if action in ("start","stop"):
        wgc_state["running"] = (action == "start")
        socketio.emit("wgc_command", {"action": action})
    if action == "set":
        sp = {k: v for k, v in (data or {}).items() if k in ("speed","valve") and v is not None}
        if sp:
            wgc_state["oper"].update(sp)
            socketio.emit("wgc_command", {"action":"set", **sp})
    socketio.emit("update_wgc", wgc_state)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5050, debug=True)
