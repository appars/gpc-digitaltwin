
# Wet Gas Compressor Digital Twin (Demo)

**Professional demo** for *Digital Twin for Wet Gas Compressor – Real-Time Monitoring & Optimization* built on Flask + Socket.IO + Chart.js.

- Simulates process & health signals:
  - **Gas Properties:** MW (from composition), composition (CH₄, C₂H₆, C₃H₈, CO₂, H₂S, H₂O), GLR, water content
  - **Operating:** T₁/T₂, P₁/P₂, flow, compression ratio, speed, valve position
  - **Health & Safety:** vibration (axial/vertical/horizontal), bearing & oil temperature, lube oil pressure, seal leakage
- Computes live **KPIs** (demo formulas): compression ratio, head index (normalized), surge margin %, efficiency index, vibration severity bands, and alarm list.
- Provides **Start/Stop** control for the simulator.

> This is a demo to show the twin loop and UI. Replace formulas/thresholds with plant/OEM standards for engineering use.

## Run

In one terminal (server + UI):
```bash
python app.py
# open http://localhost:5050/wgc
```

In another (simulator):
```bash
python wgc_sim.py
```

## Notes

- KPIs in `app.py::compute_wgc_kpis()` are **for demonstration**—tune or replace with OEM curves, surge maps, and real gas equations as needed.
- UI lives in `templates/wgc.html`. Event names: `wgc_data`, `update_wgc`, `wgc_command`.
- Simulator connects to `TWIN_URL` env var or falls back to `http://localhost:5050`.
