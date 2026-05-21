# Crosswords

Single-page web service that scrapes the daily Arabic crossword from addiyar.com and returns a combined PDF.

## Architecture
- `main.py` — FastAPI app, serves the static UI from `/` and the API under `/api/*`
- `crosswords.py` — fetch + crop + PDF assembly logic
- `static/` — single-page UI; saves user config in browser localStorage
- `config.yaml` — server-side defaults only (used the first time a browser loads the page)

The server is stateless. Each request carries `from_date`, `max_count`, `target_page`. The response includes `X-Next-Date` so the UI auto-advances for the next run.

## Run locally
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
Then open http://localhost:8000.

## Docker
```bash
docker build -t crosswords .
docker run --rm -p 8000:8000 crosswords
```

CI builds and pushes to `ghcr.io/overdrivegain/crosswords` on every push to `master`.

## Endpoints
- `GET /` — UI
- `GET /api/health` — `{"ok": true}`
- `GET /api/defaults` — defaults from `config.yaml`
- `POST /api/run` — body `{from_date, max_count, target_page}`, returns the combined PDF
- `GET /api/docs` — OpenAPI / Swagger UI
