
import os, time, random
import socketio

URL = os.getenv("TWIN_URL", "http://localhost:5050")
sio = socketio.Client(reconnection=True, reconnection_attempts=0)
running = True

@sio.event
def connect():
    print(f"[OK] Connected to {URL} (WGC sim)")

@sio.on("wgc_command")
def on_wgc_command(data):
    global running
    action = (data or {}).get("action")
    if action == "stop":
        running = False
        print("[CMD] Stop WGC simulation")
    elif action == "start":
        running = True
        print("[CMD] Start WGC simulation")
    elif action == "set":
        # server may broadcast setpoints as well; no state needed here for demo
        print("[CMD] Setpoints updated:", data)

def jitter(val, span):
    return val + random.uniform(-span, span)

def main():
    comp = {"CH4": 0.80, "C2H6": 0.07, "C3H8": 0.04, "CO2": 0.05, "H2S": 0.01, "H2O": 0.03}
    mw_map = {"CH4":16.04, "C2H6":30.07, "C3H8":44.10, "CO2":44.01, "H2S":34.08, "H2O":18.02}

    def mixture_mw(c):
        return sum(c.get(sp,0)*mw_map[sp] for sp in mw_map)

    try:
        sio.connect(URL, wait=True, transports=["websocket","polling"])
        flow = 25.0
        speed = 7800.0
        valve = 65.0
        P1, P2 = 3.0, 9.0
        T1, T2 = 300.0, 360.0
        glr = 1000.0
        water_ppm = 40
        tick = 0
        while True:
            if running:
                flow = max(10.0, jitter(flow, 0.4))
                speed = max(6000.0, jitter(speed, 30.0))
                valve = max(10.0, min(100.0, jitter(valve, 0.5)))
                P1 = max(1.5, jitter(P1, 0.02))
                P2 = max(P1*1.5, jitter(P2, 0.05))
                T1 = max(280.0, jitter(T1, 0.5))
                T2 = max(T1+20.0, jitter(T2, 0.7))
                glr = max(100.0, jitter(glr, 5.0))
                water_ppm = max(10, int(jitter(water_ppm, 2)))

                vib_axial = max(1.0, jitter(2.2, 0.4))
                vib_vert  = max(1.0, jitter(2.8, 0.6))
                vib_horz  = max(1.0, jitter(2.5, 0.5))
                if tick % 60 == 0:
                    vib_vert += random.uniform(0, 5.0)
                bearingT = jitter(345.0, 1.5)
                oilT     = jitter(325.0, 1.0)
                lubeP    = max(1.0, jitter(3.2, 0.05))
                seal_leak= max(0.0, jitter(0.12, 0.03))

                payload = {
                    "gas": {
                        "mw": mixture_mw(comp),
                        "glr": glr,
                        "water_ppm": water_ppm,
                        "composition": comp
                    },
                    "oper": {
                        "T1": T1, "T2": T2,
                        "P1": P1, "P2": P2,
                        "flow": flow,
                        "speed": speed,
                        "valve": valve
                    },
                    "health": {
                        "vib_axial": vib_axial,
                        "vib_vert": vib_vert,
                        "vib_horz": vib_horz,
                        "bearing_temp": bearingT,
                        "oil_temp": oilT,
                        "lube_oil_pressure": lubeP,
                        "seal_leakage": seal_leak
                    }
                }
                sio.emit("wgc_data", payload, namespace="/")
                print("Sent WGC:", {k: round(v,2) if isinstance(v,(int,float)) else v for k,v in payload["oper"].items()})
            else:
                print("WGC sim paused…")
            tick += 1
            time.sleep(1.5)
    except KeyboardInterrupt:
        pass
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    main()
