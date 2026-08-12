WHERE SHOULD WE EAT V3 — PROFESSIONAL

Run locally:
1. Double-click START_APP.bat
2. Open http://localhost:8000

V3 includes:
- polished mobile-first UI
- real browser geolocation
- OpenStreetMap / Overpass restaurant data
- restaurant / fast-food / cafe filters
- 1–20 km radius
- solo and group modes
- 6-character group codes
- group member list
- persistent SQLite votes locally
- winner scoring
- map links
- Render-friendly PORT environment variable

Public deployment:
The server reads PORT from the environment and binds using HOST.
For Render, set HOST=0.0.0.0 and use the service's PORT.
SQLite is suitable for testing but should be replaced with persistent hosted DB storage for production.
