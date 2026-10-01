import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import JSON, DateTime, String, create_engine
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
    url: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


def serialize(scan):
    created = scan.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "id": scan.id,
        "url": scan.url,
        "status": scan.status,
        "created_at": created.isoformat(),
        "result": scan.result,
        "error": scan.error,
    }
