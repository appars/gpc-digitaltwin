# wgc_sim.py
import os, time, random, logging
import requests

BASE = os.getenv("TWIN_URL", "http://localhost:5050").rstrip("/")
INGEST = f"{BASE}/ingest-wgc"

# Logging: quiet by default
VERBOSE = os.getenv("SIM_VERBOSE", "0") == "1"
LOG_EVERY = int(os.getenv("SIM_LOG_EVERY", "0"))  # e.g. 100 to log every 100 samples; 0 = never
logging.basicConfig(
    level=(logging.INFO if VERBOSE else logging.WARNING),
    format="[SIM] %(message)s"
)
log = logging.getLogger("sim")

def clamp(v, lo, hi): 
    return max(lo, min(hi, v))

def make_sample(t):
    # Simple synthetic dynamics
    flow  = 26 + 2.5*random.random() + 0.5*random.uniform(-1,1)
    P1    = 3.0 + 0.1*random.uniform(-1,1)
    P2    = 8.7 + 0.2*random.uniform(-1,1) + 0.05*(flow-26)
    T1    = 303.0 + 0.5*random.uniform(-1,1)
    T2    = 352.0 + 1.2*random.uniform(-1,1) + 0.15*(P2-P1)

    speed = 7800 + 80*random.uniform(-1,1)
    valve = 65 + 2.0*random.uniform(-1,1)

    v_ax   = clamp(2.0 + 1.4*random.random(), 0.2, 6.0)
    v_vert = clamp(2.1 + 1.4*random.random(), 0.2, 6.0)
    v_horz = clamp(2.2 + 1.4*random.random(), 0.2, 6.0)

    oil_p  = 3.5 + 0.2*random.uniform(-1,1)
    bt     = 340  + 1.5*random.uniform(-1,1)
    ot     = 335  + 1.5*random.uniform(-1,1)
    leak   = max(0.0, 0.2 + 0.1*random.random())

    oper = {
        "T1": round(T1,2), "T2": round(T2,2),
        "P1": round(P1,2), "P2": round(P2,2),
        "flow": round(flow,2),
        "speed": round(speed,2),
        "valve": round(valve,2),
    }
    health = {
        "v_ax": round(v_ax,2), "v_vert": round(v_vert,2), "v_horz": round(v_horz,2),
        "oil_pressure": round(oil_p,2),
        "bearing_temp": round(bt,2), "oil_temp": round(ot,2),
        "seal_leak": round(leak,2)
    }
    return {"oper": oper, "health": health}

def main():
    i = 0
    session = requests.Session()
    timeout = float(os.getenv("SIM_TIMEOUT", "3.0"))

    while True:
        i += 1
        payload = make_sample(i)
        try:
            session.post(INGEST, json=payload, timeout=timeout)
        except Exception as e:
            # Only show network errors if VERBOSE
            if VERBOSE:
                log.info("post failed: %s", e)

        if LOG_EVERY and (i % LOG_EVERY == 0):
            log.info("sent %d samples", i)

        time.sleep(1.0)

if __name__ == "__main__":
    main()

