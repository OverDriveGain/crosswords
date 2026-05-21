import datetime
import logging
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crosswords import DATE_FORMAT, build_crosswords_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

ROOT = Path(__file__).parent
app = FastAPI(title="Crosswords", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")


def _load_defaults() -> dict:
    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f) or {}
    return {
        "from_date": cfg.get("last-date", "2026/01/01"),
        "max_count": int(cfg.get("max-count", 100)),
        "target_page": int(cfg.get("target-page", 6)),
    }


class RunRequest(BaseModel):
    from_date: str = Field(pattern=r"^\d{4}/\d{2}/\d{2}$")
    max_count: int = Field(ge=1, le=500)
    target_page: int = Field(ge=0, le=50)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/defaults")
def defaults():
    return _load_defaults()


@app.post("/api/run")
def run(req: RunRequest):
    try:
        datetime.datetime.strptime(req.from_date, DATE_FORMAT)
    except ValueError:
        raise HTTPException(400, "from_date must be YYYY/MM/DD")

    pdf, processed = build_crosswords_pdf(
        from_date=req.from_date,
        max_count=req.max_count,
        target_page=req.target_page,
    )
    if not pdf:
        raise HTTPException(404, "No crosswords found in that range")

    next_date = (
        datetime.datetime.strptime(processed[-1], DATE_FORMAT)
        + datetime.timedelta(days=1)
    ).strftime(DATE_FORMAT)
    fname = f"crosswords-{processed[0].replace('/', '-')}_to_{processed[-1].replace('/', '-')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Access-Control-Expose-Headers": "X-Processed-Count, X-First-Date, X-Last-Date, X-Next-Date",
            "X-Processed-Count": str(len(processed)),
            "X-First-Date": processed[0],
            "X-Last-Date": processed[-1],
            "X-Next-Date": next_date,
        },
    )


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
