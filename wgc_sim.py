#!/usr/bin/env python3
import os
import time
import math
import random
import argparse
import requests

def clip(v, lo, hi): return max(lo, min(hi, v))

def main():
    ap = argparse.ArgumentParser(description="WGC external simulator -> /ingest-wgc")
    ap.add_argument("--base", default=os.getenv("WGC_URL", "http://localhost:5050"),
                    help="Server base URL (default %(default)s)")
    ap.add_argument("--hz", type=float, default=1.0, help="Send rate in Hz (default 1.0)")
    ap.add_argument("--quiet", action="store_true", help="Less console output")
    args = ap.parse_args()

    url = args.base.rstrip("/") + "/ingest-wgc"
    dt = 1.0 / max(0.1, args.hz)

    # initial conditions
    speed = 7800.0
    valve = 65.0
    flow = 25.0
    P1 = 3.0
    P2 = 8.8

    t0 = time.perf_counter()
    sent = 0
    print(f"[SIM] Posting to {url} at {args.hz:.2f} Hz (Ctrl+C to stop)")
    try:
        while True:
            t = time.perf_counter() - t0

            # simple wandering setpoints
            speed = 7800 + 300 * math.sin(t * 0.05)
            valve = 65 + 5 * math.sin(t * 0.08 + 1.0)

            # synthesize process
            target_flow = 0.0026 * speed + 0.18 * (valve / 100.0) * 30.0
            flow += (target_flow - flow) * 0.15 + random.uniform(-0.2, 0.2)
            flow = clip(flow, 20.0, 42.0)

            P1 = 3.0 + 0.06 * math.sin(t * 0.12) + random.uniform(-0.05, 0.05)
            dP = 0.006 * speed + 0.04 * (valve / 100.0) * 30.0 - 1.5
            P2 = clip(P1 + dP, 6.5, 11.5)

            T1 = 303.0 + random.uniform(-0.5, 0.5)
            T2 = 352.0 + 0.02 * (P2 - P1) * 100 + random.uniform(-0.6, 0.6)

            base_vib = 1.8 + 0.00012 * speed + 0.04 * max(0.0, (P2 - P1) - 5.0)
            v_ax   = clip(base_vib + random.uniform(-0.4, 0.4), 0.6, 8.5)
            v_vert = clip(base_vib + random.uniform(-0.3, 0.5), 0.6, 8.5)
            v_horz = clip(base_vib + random.uniform(-0.3, 0.4), 0.6, 8.5)
            oil_p  = clip(3.1 + 0.0005 * (speed - 7600) + random.uniform(-0.05, 0.05), 2.4, 4.5)
            brg_t  = clip(340.0 + 0.004 * speed + random.uniform(-0.6, 0.8), 330.0, 385.0)
            oil_t  = clip(323.0 + 0.002 * speed + random.uniform(-0.6, 0.8), 320.0, 370.0)
            leak   = clip(0.10 + 0.00003 * (speed - 7000) + random.uniform(-0.01, 0.01), 0.0, 0.6)

            payload = {
                "wgc": {
                    "oper": {"T1": T1, "T2": T2, "P1": P1, "P2": P2, "flow": flow, "speed": speed, "valve": valve},
                    "health": {"v_ax": v_ax, "v_vert": v_vert, "v_horz": v_horz,
                               "oil_pressure": oil_p, "bearing_temp": brg_t, "oil_temp": oil_t, "seal_leak": leak}
                }
            }

            try:
                r = requests.post(url, json=payload, timeout=3)
                if r.status_code != 200 and not args.quiet:
                    print(f"[SIM] POST -> {r.status_code} {r.text[:120]}")
            except Exception as e:
                if not args.quiet:
                    print(f"[SIM] POST error: {e}")

            sent += 1
            if not args.quiet and sent % 10 == 0:
                print(f"[SIM] sent {sent} samples")

            time.sleep(dt)
    except KeyboardInterrupt:
        print("\n[SIM] stopped")


if __name__ == "__main__":
    main()

