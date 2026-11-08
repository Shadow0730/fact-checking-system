"""ORM tables mirroring db/init.sql. The schema itself is created by init.sql."""
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(Text)
    court: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(Text, default="en")
    citations: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    citation_keys: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    file_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    ord: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    para: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    # `tsv` is a generated column in SQL; it is not mapped here (read only via raw SQL).
    embedding = mapped_column(Vector(settings.embedding_dim), deferred=True)  # only loaded when asked for


class Check(Base):
    __tablename__ = "checks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(Text)
    input_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="running")
    summary: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    check_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checks.id", ondelete="CASCADE"))
    ord: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(Text)
    citation_raw: Mapped[str | None] = mapped_column(Text)
    citation_key: Mapped[str | None] = mapped_column(Text)
    citation_status: Mapped[str | None] = mapped_column(Text)
    case_name: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    quote_text: Mapped[str | None] = mapped_column(Text)
    quote_score: Mapped[float | None] = mapped_column(Float)
    quote_match: Mapped[str | None] = mapped_column(Text)
    quote_diff: Mapped[list | None] = mapped_column(JSONB)
    quote_critical: Mapped[bool | None] = mapped_column(Boolean)
    support_probs: Mapped[dict | None] = mapped_column(JSONB)
    evidence_chunk: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    verdict: Mapped[str] = mapped_column(Text)
    colour: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    fix: Mapped[dict | None] = mapped_column(JSONB)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dataset: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB)
    metrics: Mapped[dict] = mapped_column(JSONB)
