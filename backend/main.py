import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select, update

from database import Base, Scan, Session, engine, serialize, initialize_database
from auth import require_user
from explain import explain_scan
from scanner import ScanError, validate_url
from crawler import scan_website

logger = logging.getLogger(__name__)
tasks = set()
slots = asyncio.Semaphore(max(1, min(3, int(os.getenv("MAX_CONCURRENT_SCANS", "3")))))


@asynccontextmanager
async def lifespan(app):
    initialize_database(engine)
    with Session.begin() as db:
        db.execute(
            update(Scan)
            .where(Scan.status.in_(["queued", "running"]))
            .values(
                status="failed",
                error="The server restarted before this scan finished. Please run it again.",
            )
        )
    yield
    for task in list(tasks):
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Site Scan API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/scans"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


class ScanRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return validate_url(value)


async def run_scan(scan_id, url):
    async with slots:
        with Session.begin() as db:
            scan = db.get(Scan, scan_id)
            scan.status = "running"
        try:
            result = await scan_website(url)
            with Session.begin() as db:
                scan = db.get(Scan, scan_id)
                scan.result = result
                scan.status = "completed"
        except Exception as exc:
            if not isinstance(exc, ScanError):
                logger.exception("Scan failed: %s", scan_id)
            with Session.begin() as db:
                scan = db.get(Scan, scan_id)
                scan.status = "failed"
                scan.error = (
                    str(exc)
                    if isinstance(exc, ScanError)
                    else "The scan could not be completed. Please try again."
                )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scans", status_code=202)
async def create_scan(request: ScanRequest, owner_id: str = Depends(require_user)):
    if len(tasks) >= 12:
        raise HTTPException(429, "The scan queue is full. Please try again shortly.")
    with Session.begin() as db:
        scan = Scan(url=request.url, owner_id=owner_id)
        db.add(scan)
        db.flush()
        response = serialize(scan)
    task = asyncio.create_task(run_scan(scan.id, scan.url))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return response


@app.get("/scans")
def list_scans(owner_id: str = Depends(require_user)):
    with Session() as db:
        return [
            serialize(scan)
            for scan in db.scalars(
                select(Scan).where(Scan.owner_id == owner_id).order_by(Scan.created_at.desc()).limit(100)
            )
        ]


@app.get("/scans/{scan_id}")
def get_scan(scan_id: str, owner_id: str = Depends(require_user)):
    with Session() as db:
        scan = db.get(Scan, scan_id)
        if scan is None or scan.owner_id != owner_id:
            raise HTTPException(404, "Scan not found.")
        return serialize(scan)


@app.post("/scans/{scan_id}/explain")
async def explain(scan_id: str, owner_id: str = Depends(require_user)):
    with Session() as db:
        scan = db.get(Scan, scan_id)
        if scan is None or scan.owner_id != owner_id:
            raise HTTPException(404, "Scan not found.")
        if scan.status != "completed" or not scan.result:
            raise HTTPException(409, "The scan has not finished yet.")
        result = scan.result
    if result.get("explanation"):
        return result["explanation"]
    explanation = await explain_scan(result)
    if explanation["source"] == "ai":
        with Session.begin() as db:
            scan = db.get(Scan, scan_id)
            scan.result = {**scan.result, "explanation": explanation}
    return explanation


@app.get("/scans/{scan_id}/export")
def export_scan(scan_id: str, owner_id: str = Depends(require_user)):
    with Session() as db:
        scan = db.get(Scan, scan_id)
        if scan is None or scan.owner_id != owner_id:
            raise HTTPException(404, "Scan not found.")
        return JSONResponse(
            serialize(scan),
            headers={
                "Content-Disposition": f'attachment; filename="site-scan-{scan.id}.json"'
            },
        )
