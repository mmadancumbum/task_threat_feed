import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, String, Integer, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from datetime import datetime, timezone

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
database_url = os.getenv('DATABASE_URL')
if not database_url:
    raise RuntimeError('Set DATABASE_URL in backend/.env or the process environment.')
engine = create_engine(database_url, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
DATA_DIR = Path(os.getenv('DATA_DIR', str(Path(__file__).resolve().parents[2] / 'data' / 'uploads'))).resolve()

class Base(DeclarativeBase):
    pass

class Indicator(Base):
    __tablename__ = 'indicators'
    # SHA-256 of type + separator + normalized value avoids MySQL URL index limits.
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(10), index=True)
    value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(255))
    first_seen: Mapped[datetime] = mapped_column(DateTime)

class Job(Base):
    __tablename__ = 'ingestion_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(12), default='queued', index=True)
    size: Mapped[int] = mapped_column(Integer)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new: Mapped[int] = mapped_column(Integer, default=0)
    merged: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class RowError(Base):
    __tablename__ = 'row_errors'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('ingestion_jobs.id'), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500))
