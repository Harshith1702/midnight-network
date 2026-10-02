# Midnight Network

Small HTTP service monitor. It checks URLs on an interval, stores every check in SQLite, opens an incident when a service goes down and closes it when it recovers. All numbers on the dashboard come from stored checks.

## Run locally
```
pip install -r requirements.txt
python app.py            # http://127.0.0.1:8000
python -m pytest -q      # tests
```
## Run with Docker
```
docker compose up --build   # http://localhost:8000, data in ./data
```
## Config (env vars, see .env.example)
`PORT`, `DB_PATH`, `CHECK_TIMEOUT` (s), `MIN_INTERVAL` (s), `ALLOW_PRIVATE_TARGETS` (default false).

## Architecture
- `app.py` Flask routes + JSON API, serves `static/`
- `monitor.py` URL validation, HTTP check, incident logic, uptime, scheduler thread
- `db.py` SQLite schema (services, checks, incidents)
- `GET /health` reports the app itself is running (used by the Docker healthcheck)
- CI: `.github/workflows/ci.yml` runs pytest on every push

Incident logic: a failed check on a service not already DOWN opens an incident. The next successful check closes it and stores the duration. Open incidents survive restarts since status lives in the DB.

## Features
Add/stop/start/remove services, per-service interval, dashboard counts, uptime %, response time chart, service detail (checks, status changes, incidents).

## Limitations
- UP means HTTP status below 400. Redirects are not followed (3xx counts as up).
- A DOWN result means the HTTP request failed. It does not say which network hop is at fault.
- Private, loopback and link-local targets are blocked by resolving the host before each check. DNS can change between resolve and connect, so this is not a full SSRF guarantee.
- No auth, no alerts, no data retention limit, single worker.

## Demo
1. Start a local target: `python -m http.server 9000`
2. Run the app with `ALLOW_PRIVATE_TARGETS=true MIN_INTERVAL=10 python app.py` (Docker: use `http://host.docker.internal:9000` with the same env var)
3. Add `http://127.0.0.1:9000`, interval 10. Wait for a green check.
4. Stop the target (Ctrl+C). Within one interval an incident opens and the service turns red.
5. Start it again. The incident closes and shows the downtime duration.
6. Restart the app: services, history and incidents are still there.
