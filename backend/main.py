import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, update

from database import (
    Base,
    Monitor,
    Notification,
    Scan,
    Session,
    engine,
    initialize_database,
    serialize,
    serialize_monitor,
    serialize_notification,
    UserPreference,
)
from auth import require_user, session_email
from explain import explain_scan
from scanner import ScanError, validate_url
from crawler import scan_website
from monitors import (
    FAILURES_BEFORE_ALERT,
    FREQUENCIES,
    MAX_MONITORS_PER_USER,
    RETRY_AFTER_FAILURE,
    failure_alert,
    issues_alert,
    new_issues,
    recovery_alert,
    send_email,
)

logger = logging.getLogger(__name__)
tasks = set()
MAX_QUEUED_SCANS = 12
SCHEDULER_SECONDS = 60
slots = asyncio.Semaphore(max(1, min(3, int(os.getenv("MAX_CONCURRENT_SCANS", "3")))))


@asynccontextmanager
async def lifespan(app):
    initialize_database(engine)
    with Session.begin() as db:
        interrupted = db.execute(
            select(Scan.owner_id, Scan.url).where(Scan.status.in_(["queued", "running"]))
        ).all()
        # Delayed so a scan that crashes the server cannot cause a restart loop.
        retry_at = datetime.now(timezone.utc) + RETRY_AFTER_FAILURE
        for owner_id, url in set(interrupted):
            db.execute(
                update(Monitor)
                .where(Monitor.owner_id == owner_id, Monitor.url == url, Monitor.active)
                .values(next_run_at=retry_at)
            )
        db.execute(
            update(Scan)
            .where(Scan.status.in_(["queued", "running"]))
            .values(
                status="failed",
                error="The server restarted before this scan finished. Please run it again.",
            )
        )
    scheduler_task = asyncio.create_task(scheduler())
    yield
    scheduler_task.cancel()
    await asyncio.gather(scheduler_task, return_exceptions=True)
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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/scans", "/monitors", "/notifications", "/preferences")):
        response.headers["Cache-Control"] = "private, no-store"
    return response


class ScanRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        return validate_url(value)


class MonitorRequest(ScanRequest):
    frequency: Literal["daily", "weekly"] = "daily"


class MonitorUpdate(BaseModel):
    active: bool


async def run_scan(scan_id, url, monitor_id=None, scheduled=True):
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
    if monitor_id:
        try:
            await finish_monitor_run(monitor_id, scan_id, scheduled=scheduled)
        except Exception:
            logger.exception("Monitor follow-up failed: %s", monitor_id)


def start_scan(scan_id, url, monitor_id=None, scheduled=True):
    task = asyncio.create_task(run_scan(scan_id, url, monitor_id, scheduled))
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def run_due_monitors():
    now = datetime.now(timezone.utc)
    started = []
    with Session.begin() as db:
        due = db.scalars(
            select(Monitor)
            .where(Monitor.active, Monitor.next_run_at <= now)
            .order_by(Monitor.next_run_at)
            .limit(max(0, MAX_QUEUED_SCANS - len(tasks)))
        )
        for monitor in due:
            if active_monitor_scan(db, monitor.id):
                continue
            monitor.next_run_at = now + FREQUENCIES[monitor.frequency]
            scan = Scan(url=monitor.url, owner_id=monitor.owner_id, monitor_id=monitor.id)
            db.add(scan)
            db.flush()
            started.append((scan.id, monitor.url, monitor.id))
    for run in started:
        start_scan(*run)


async def scheduler():
    while True:
        try:
            run_due_monitors()
        except Exception:
            logger.exception("Scheduled scan check failed")
        await asyncio.sleep(SCHEDULER_SECONDS)


async def finish_monitor_run(monitor_id, scan_id, scheduled=True):
    alerts = []
    with Session.begin() as db:
        monitor = db.get(Monitor, monitor_id)
        scan = db.get(Scan, scan_id, with_for_update=True)
        if monitor is None or scan is None:
            return
        email = monitor.email
        if scan.status == "failed":
            monitor.failures += 1
            if monitor.failures < FAILURES_BEFORE_ALERT and scheduled:
                monitor.next_run_at = datetime.now(timezone.utc) + RETRY_AFTER_FAILURE
            elif monitor.failures == FAILURES_BEFORE_ALERT:
                alerts.append(failure_alert(monitor.url, scan.error))
        else:
            if monitor.failures >= FAILURES_BEFORE_ALERT:
                alerts.append(recovery_alert(monitor.url))
            monitor.failures = 0
            previous = db.scalars(
                select(Scan)
                .where(
                    Scan.owner_id == monitor.owner_id,
                    Scan.monitor_id == monitor.id,
                    Scan.status == "completed",
                    Scan.id != scan.id,
                    Scan.created_at < scan.created_at,
                )
                .order_by(Scan.created_at.desc())
                .limit(1)
            ).first()
            issues = new_issues(scan.result, previous.result) if previous else []
            if issues:
                alerts.append(issues_alert(monitor.url, issues))
        for alert in alerts:
            db.add(
                Notification(
                    owner_id=monitor.owner_id,
                    url=monitor.url,
                    scan_id=scan.id,
                    **alert,
                )
            )
    for alert in alerts:
        await send_email(email, alert["title"], alert["body"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scans", status_code=202)
async def create_scan(request: ScanRequest, owner_id: str = Depends(require_user)):
    if len(tasks) >= MAX_QUEUED_SCANS:
        raise HTTPException(429, "The scan queue is full. Please try again shortly.")
    with Session.begin() as db:
        scan = Scan(url=request.url, owner_id=owner_id)
        db.add(scan)
        db.flush()
        response = serialize(scan)
    start_scan(scan.id, scan.url)
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
            saved = db.execute(
                update(Scan)
                .where(Scan.id == scan_id, Scan.owner_id == owner_id)
                .values(result={**result, "explanation": explanation})
            )
            if saved.rowcount == 0:
                raise HTTPException(404, "Scan not found.")
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


@app.delete("/scans/{scan_id}")
async def delete_scan(scan_id: str, owner_id: str = Depends(require_user)):
    with Session.begin() as db:
        scan = db.get(Scan, scan_id, with_for_update=True)
        if scan is None or scan.owner_id != owner_id:
            raise HTTPException(404, "Scan not found.")
        # A running scan still writes its result to this row, so wait for it to finish.
        if scan.status in ("queued", "running"):
            raise HTTPException(409, "This scan is still running. Delete it after it finishes.")
        db.execute(
            delete(Notification).where(
                Notification.scan_id == scan.id, Notification.owner_id == owner_id
            )
        )
        db.delete(scan)
    return {"deleted": True}


def active_monitor_scan(db, monitor_id):
    return db.scalar(select(Scan.id).where(
        Scan.monitor_id == monitor_id,
        Scan.status.in_(["queued", "running"]),
    ).limit(1))


@app.post("/monitors/{monitor_id}/scan", status_code=202)
async def scan_monitor_now(monitor_id: str, owner_id: str = Depends(require_user)):
    with Session.begin() as db:
        monitor = db.get(Monitor, monitor_id)
        if monitor is None or monitor.owner_id != owner_id:
            raise HTTPException(404, "Monitor not found.")
        if active_monitor_scan(db, monitor_id):
            raise HTTPException(409, "A scan is already queued or running for this website.")
        if len(tasks) >= MAX_QUEUED_SCANS:
            raise HTTPException(429, "The scan queue is full. Please try again shortly.")
        scan = Scan(url=monitor.url, owner_id=owner_id, monitor_id=monitor_id)
        db.add(scan)
        db.flush()
        response = serialize(scan)
    start_scan(scan.id, scan.url, monitor_id, scheduled=False)
    return response


@app.get("/monitors")
def list_monitors(owner_id: str = Depends(require_user)):
    with Session() as db:
        return [
            serialize_monitor(monitor, active_monitor_scan(db, monitor.id))
            for monitor in db.scalars(
                select(Monitor)
                .where(Monitor.owner_id == owner_id)
                .order_by(Monitor.created_at.desc())
            )
        ]


@app.post("/monitors", status_code=201)
async def create_monitor(
    request: MonitorRequest,
    owner_id: str = Depends(require_user),
    email: str | None = Depends(session_email),
):
    with Session.begin() as db:
        existing = db.scalars(select(Monitor).where(Monitor.owner_id == owner_id)).all()
        if any(monitor.url == request.url for monitor in existing):
            raise HTTPException(409, "This website is already being monitored.")
        if len(existing) >= MAX_MONITORS_PER_USER:
            raise HTTPException(
                409, f"You can monitor up to {MAX_MONITORS_PER_USER} websites."
            )
        monitor = Monitor(
            owner_id=owner_id,
            url=request.url,
            frequency=request.frequency,
            email=email,
            next_run_at=datetime.now(timezone.utc),
        )
        db.add(monitor)
        db.flush()
        monitor_id = monitor.id
    run_due_monitors()
    with Session() as db:
        return serialize_monitor(db.get(Monitor, monitor_id), active_monitor_scan(db, monitor_id))


@app.patch("/monitors/{monitor_id}")
def update_monitor(
    monitor_id: str, request: MonitorUpdate, owner_id: str = Depends(require_user)
):
    with Session.begin() as db:
        monitor = db.get(Monitor, monitor_id)
        if monitor is None or monitor.owner_id != owner_id:
            raise HTTPException(404, "Monitor not found.")
        monitor.active = request.active
        db.flush()
        return serialize_monitor(monitor, active_monitor_scan(db, monitor.id))


@app.delete("/monitors/{monitor_id}")
def delete_monitor(monitor_id: str, owner_id: str = Depends(require_user)):
    with Session.begin() as db:
        monitor = db.get(Monitor, monitor_id)
        if monitor is None or monitor.owner_id != owner_id:
            raise HTTPException(404, "Monitor not found.")
        db.delete(monitor)
    return {"deleted": True}


@app.get("/notifications")
def list_notifications(owner_id: str = Depends(require_user)):
    with Session() as db:
        return [
            serialize_notification(notification)
            for notification in db.scalars(
                select(Notification)
                .where(Notification.owner_id == owner_id)
                .order_by(Notification.created_at.desc())
                .limit(50)
            )
        ]


@app.post("/notifications/read")
def mark_notifications_read(owner_id: str = Depends(require_user)):
    with Session.begin() as db:
        db.execute(
            update(Notification)
            .where(Notification.owner_id == owner_id, Notification.read.is_(False))
            .values(read=True)
        )
    return {"read": True}

ThemeName = Literal[
    "light",
    "dark",
    "navy",
    "pink",
    "lavender",
    "forest",
    "confetti",
    "red-void",
]

ThemeSelection = Literal[
    "light",
    "dark",
    "navy",
    "pink",
    "lavender",
    "forest",
    "confetti",
    "red-void",
    "systematic",
]

TextColor = Literal[
    "off",
    "white",
    "off-white",
    "black",
]

class PreferencesUpdate(BaseModel):
    theme: ThemeSelection

    day_theme: ThemeName = "light"

    night_theme: ThemeName = "dark"

    day_start: str = Field(
        default="07:00",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )

    night_start: str = Field(
        default="19:00",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )

    text_color: TextColor = "off"

@app.get("/preferences")
def get_preferences(
    owner_id: str = Depends(require_user),
):
    with Session() as session:
        preference = session.get(UserPreference, owner_id)

        if preference is None:
            return {
                "theme": "dark",
                "day_theme": "light",
                "night_theme": "dark",
                "day_start": "07:00",
                "night_start": "19:00",
                "text_color": "off",
            }

        return {
            "theme": preference.theme,
            "day_theme": preference.day_theme,
            "night_theme": preference.night_theme,
            "day_start": preference.day_start,
            "night_start": preference.night_start,
            "text_color": preference.text_color,
        }

@app.put("/preferences")
def update_preferences(
    payload: PreferencesUpdate,
    owner_id: str = Depends(require_user),
):
    with Session() as session:
        preference = session.get(UserPreference, owner_id)

        if preference is None:
            preference = UserPreference(
                owner_id=owner_id,
                theme=payload.theme,
                day_theme=payload.day_theme,
                night_theme=payload.night_theme,
                day_start=payload.day_start,
                night_start=payload.night_start,
                text_color=payload.text_color,
            )

            session.add(preference)

        else:
            preference.theme = payload.theme
            preference.day_theme = payload.day_theme
            preference.night_theme = payload.night_theme
            preference.day_start = payload.day_start
            preference.night_start = payload.night_start
            preference.text_color = payload.text_color

        session.commit()
        session.refresh(preference)

        return {
            "theme": preference.theme,
            "day_theme": preference.day_theme,
            "night_theme": preference.night_theme,
            "day_start": preference.day_start,
            "night_start": preference.night_start,
            "text_color": preference.text_color,
        }
