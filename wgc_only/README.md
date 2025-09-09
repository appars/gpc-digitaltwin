# Wet Gas Compressor Digital Twin (WGC-only)

A focused, client-ready **Digital Twin** for a **Wet Gas Compressor** with real-time KPIs, alarms, setpoints, and CSV export.

## Run
```bash
python app.py
# open http://localhost:5050  (redirects to /wgc)
```
In another terminal:
```bash
python wgc_sim.py
```

## Notes
- Replace demo KPIs in `compute_wgc_kpis()` with your plant/OEM formulas when available.
- Endpoints: `/api/wgc/history.csv`, `/api/wgc/clear`.
- Events: `wgc_data`, `update_wgc`, `wgc_command`.
