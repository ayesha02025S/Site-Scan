import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
database_url = os.getenv(
    "DATABASE_URL", f'sqlite:///{ROOT / "backend" / "sitescan.db"}'
)
if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:////"):
    relative = database_url.removeprefix("sqlite:///")
    if relative != ":memory:":
        database_url = f'sqlite:///{ROOT / "backend" / relative}'
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(
    database_url,
    connect_args=(
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    ),
    pool_pre_ping=True,
)
Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    monitor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Monitor(Base):
    __tablename__ = "monitors"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    frequency: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    scan_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def iso_utc(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def serialize(scan):
    return {
        "id": scan.id,
        "url": scan.url,
        "status": scan.status,
        "created_at": iso_utc(scan.created_at),
        "result": scan.result,
        "error": scan.error,
    }


def serialize_monitor(monitor, active_scan_id=None):
    return {
        "id": monitor.id,
        "url": monitor.url,
        "active_scan_id": active_scan_id,
        "email_enabled": bool(monitor.email and os.getenv("RESEND_API_KEY") and os.getenv("NOTIFICATION_FROM_EMAIL")),
        "frequency": monitor.frequency,
        "active": monitor.active,
        "email": monitor.email,
        "next_run_at": iso_utc(monitor.next_run_at),
        "created_at": iso_utc(monitor.created_at),
    }


def serialize_notification(notification):
    return {
        "id": notification.id,
        "url": notification.url,
        "scan_id": notification.scan_id,
        "kind": notification.kind,
        "title": notification.title,
        "body": notification.body,
        "read": notification.read,
        "created_at": iso_utc(notification.created_at),
    }


def initialize_database(bind):
    Base.metadata.create_all(bind)
    with bind.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("scans")}
        if "owner_id" not in columns:
            connection.execute(text("ALTER TABLE scans ADD COLUMN owner_id VARCHAR(255)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_scans_owner_id ON scans (owner_id)"))
        if "monitor_id" not in columns:
            connection.execute(text("ALTER TABLE scans ADD COLUMN monitor_id VARCHAR(36)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_scans_monitor_id ON scans (monitor_id)"))
