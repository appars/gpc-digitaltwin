#!/usr/bin/env python3
import os, time, math, random, argparse

# Optional deps
try:
    import socketio  # python-socketio client
except Exception:
    socketio = None
try:
    import requests
except Exception:
    requests = None

def build_sample(t):
    T1 = 303.0 + 0.4*math.sin(t/17.0)
    T2 = 352.0 + 0.6*math.sin(t/15.0 + 0.9)
    P1 = 3.00 + 0.08*math.sin(t/21.0)
    P2 = 8.75 + 0.10*math.sin(t/19.0 + 1.2)
    flow = 25.6 + 0.7*math.sin(t/13.0 + 0.4)
    speed = 7800 + 80*math.sin(t/23.0 + 0.6)
    valve = 65 + 1.0*math.sin(t/29.0)

    vib_ax = 2.2 + 0.5*math.sin(t/11.0)
    vib_v  = 2.6 + 0.6*math.sin(t/9.0 + 0.5)
    vib_h  = 2.4 + 0.5*math.sin(t/7.0 + 1.0)
    bearing = 344.0 + 1.2*math.sin(t/16.0)
    oil_t   = 325.0 + 0.8*math.sin(t/18.0)
    lube_p  = 3.10 + 0.12*math.sin(t/20.0)
    seal    = 0.10 + 0.02*math.sin(t/24.0)

    oper = {"T1": round(T1,2), "T2": round(T2,2), "P1": round(P1,2), "P2": round(P2,2),
            "flow": round(flow,2), "speed": round(speed,2), "valve": round(valve,2)}
    health = {"vib_axial": round(vib_ax,2), "vib_vert": round(vib_v,2), "vib_horz": round(vib_h,2),
              "bearing_temp": round(bearing,2), "oil_temp": round(oil_t,2),
              "lube_oil_pressure": round(lube_p,2), "seal_leakage": round(seal,3)}
    return {"oper": oper, "health": health}

def main():
    ap = argparse.ArgumentParser(description="WGC demo simulator")
    ap.add_argument("--url", default=os.getenv("TWIN_URL", "http://127.0.0.1:5050"),
                    help="Base URL (default env TWIN_URL or http://127.0.0.1:5050)")
    ap.add_argument("-i","--interval", type=float, default=1.0, help="sample period seconds")
    ap.add_argument("-q","--quiet", action="store_true", help="suppress per-sample prints")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    QUIET = args.quiet or os.getenv("QUIET", "1") == "1"  # default: quiet

    sio = None
    ws_ok = False
    if socketio:
        try:
            sio = socketio.Client(reconnection=True, request_timeout=5)
            sio.connect(base, transports=["websocket","polling"])
            ws_ok = True
            if not QUIET: print(f"[OK] Connected WS -> {base}")
        except Exception as e:
            if not QUIET: print(f"[WARN] WS connect failed ({e}); using HTTP fallback")

    t0 = time.time()
    while True:
        t = time.time() - t0
        payload = build_sample(t)

        sent = False
        if ws_ok and sio:
            try:
                sio.emit("wgc_data", payload)
                sent = True
            except Exception as e:
                if not QUIET: print(f"[WARN] WS emit failed: {e}")
                ws_ok = False

        if not sent and requests:
            try:
                requests.post(f"{base}/api/wgc/ingest", json=payload, timeout=2)
            except Exception as e:
                if not QUIET: print(f"[ERR] HTTP ingest failed: {e}")

        if not QUIET:
            flat = {**payload["oper"]}
            print("Sent WGC:", {k: round(v,2) for k,v in flat.items()})

        time.sleep(max(0.05, args.interval))

if __name__ == "__main__":
    main()

