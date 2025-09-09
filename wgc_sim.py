# wgc_sim.py
import os, random, time, math
import socketio

# Optional HTTP fallback
try:
    import requests
except Exception:
    requests = None

URL = os.getenv("TWIN_URL", "http://localhost:5050")
WS_URL = URL  # same origin

sio = socketio.Client(reconnection=True, reconnection_attempts=0)

running = True
sp_speed = 7800.0
sp_valve = 65.0

def jitter(val, span):  # ±span%
    return val * (1.0 + random.uniform(-span, span) / 100.0)

@sio.event
def connect():
    print(f"[OK] Connected to {WS_URL}")

@sio.event
def disconnect():
    print("[WS] Disconnected")

@sio.on("wgc_command")
def on_wgc_command(msg):
    global running, sp_speed, sp_valve
    action = (msg or {}).get("action")
    if action == "stop":
        running = False
        print("[CMD] stop → running = False")
    elif action == "start":
        running = True
        print("[CMD] start → running = True")
    elif action == "set":
        if "speed" in msg: sp_speed = float(msg["speed"])
        if "valve" in msg: sp_valve = float(msg["valve"])
        print(f"[CMD] set → speed={sp_speed:.1f}, valve={sp_valve:.1f}")

def build_payload(t):
    speed = jitter(sp_speed, 1.0)
    valve = max(0.0, min(100.0, jitter(sp_valve, 1.0)))
    flow  = max(10.0, 18.0 + 0.12 * valve + random.uniform(-0.5, 0.5))
    P1    = 3.0  + random.uniform(-0.05, 0.05)
    P2    = 8.8  + 0.0015 * (speed - 7800.0) + random.uniform(-0.05, 0.05)
    T1    = 303.0 + random.uniform(-0.5, 0.5)
    T2    = 352.0 + 0.004 * (speed - 7800.0) + random.uniform(-0.6, 0.6)

    base_vib = 2.2 + 0.0003 * (speed - 7800.0)
    vib_axial = max(1.5, base_vib + 0.3 * math.sin(t/7.0) + random.uniform(-0.3, 0.3))
    vib_vert  = max(1.5, base_vib + 0.4 * math.cos(t/9.0) + random.uniform(-0.3, 0.3))
    vib_horz  = max(1.5, base_vib + 0.2 * math.sin(t/5.0) + random.uniform(-0.3, 0.3))
    oil_p     = 3.1 + random.uniform(-0.1, 0.1)
    bearingT  = 344.0 + 0.003 * (speed - 7800.0) + random.uniform(-0.5, 0.5)
    oilT      = 325.0 + random.uniform(-0.4, 0.4)
    seal      = max(0.05, 0.10 + random.uniform(-0.03, 0.05))

    return {
        "oper": {
            "T1": T1, "T2": T2, "P1": P1, "P2": P2,
            "flow": flow, "speed": speed, "valve": valve
        },
        "health": {
            "vib_axial": vib_axial, "vib_vert": vib_vert, "vib_horz": vib_horz,
            "lube_oil_pressure": oil_p, "bearing_temp": bearingT, "oil_temp": oilT,
            "seal_leakage": seal
        }
    }

def http_ingest(payload):
    if not requests:
        print("[WARN] requests not installed; HTTP fallback disabled")
        return
    try:
        r = requests.post(f"{URL}/api/wgc/ingest", json=payload, timeout=3)
        if r.ok:
            print("HTTP ingest ✓", {k: round(v,2) for k,v in payload["oper"].items()})
        else:
            print("HTTP ingest ✗", r.status_code)
    except Exception as e:
        print("HTTP ingest error:", e)

def main():
    try:
        sio.connect(WS_URL, transports=["websocket", "polling"])
        while not sio.connected:
            time.sleep(0.1)
        print(f"[READY] Streaming to {WS_URL}")
    except Exception as e:
        print("[WARN] WS connect failed:", e)

    t = 0
    try:
        while True:
            if running:
                payload = build_payload(t)
                if sio.connected:
                    sio.emit("wgc_data", payload)
                    print("Sent WGC:", {k: round(v,2) for k,v in payload["oper"].items()})
                else:
                    http_ingest(payload)
            time.sleep(1.0)
            t += 1
    except KeyboardInterrupt:
        pass
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    main()

