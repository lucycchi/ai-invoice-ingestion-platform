"""The app's tables, as described in the architecture's database section."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db import Money


class Base(DeclarativeBase):
    pass


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    status_reason: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    stored_path: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(64))
    uploaded_at: Mapped[str] = mapped_column(String(32))
    confirmed_sponsor_id: Mapped[int | None] = mapped_column(Integer)
    confirmed_study_id: Mapped[int | None] = mapped_column(Integer)
    confirmed_site_id: Mapped[int | None] = mapped_column(Integer)
    confirmed_names: Mapped[str | None] = mapped_column(Text)
    finalize_summary: Mapped[str | None] = mapped_column(Text)
    finalized_at: Mapped[str | None] = mapped_column(String(32))


class Extraction(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), unique=True)
    is_invoice: Mapped[bool]
    header: Mapped[str] = mapped_column(Text)
    printed_total: Mapped[Decimal | None] = mapped_column(Money)
    arithmetic_warnings: Mapped[str] = mapped_column(Text, default="[]")
    raw_answer: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))


class LineItem(Base):
    __tablename__ = "line_items"
    __table_args__ = (UniqueConstraint("invoice_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    position: Mapped[int]
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None]
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    amount: Mapped[Decimal | None] = mapped_column(Money)


class MetadataSuggestion(Base):
    __tablename__ = "metadata_suggestions"
    __table_args__ = (UniqueConstraint("invoice_id", "field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    field: Mapped[str] = mapped_column(String(16))
    entity_id: Mapped[int | None]
    entity_name: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[str] = mapped_column(Text, default="[]")


class CatalogSnapshotItem(Base):
    __tablename__ = "catalog_snapshot"
    __table_args__ = (UniqueConstraint("invoice_id", "catalog_item_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    catalog_item_id: Mapped[int]
    item_code: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)


class LineMatch(Base):
    __tablename__ = "line_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_item_id: Mapped[int] = mapped_column(ForeignKey("line_items.id"), unique=True)
    ai_catalog_item_id: Mapped[int | None]
    ai_confidence: Mapped[str] = mapped_column(String(8))
    ai_reason: Mapped[str] = mapped_column(Text)
    ai_alternatives: Mapped[str] = mapped_column(Text, default="[]")
    override_kind: Mapped[str] = mapped_column(String(16), default="none")
    override_catalog_item_id: Mapped[int | None]
    price_flag: Mapped[str | None] = mapped_column(Text)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    step: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str] = mapped_column(String(32))
    stored_at: Mapped[str | None] = mapped_column(String(32))
    shown_at: Mapped[str | None] = mapped_column(String(32))
    claude_requests: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    cache_applied: Mapped[bool] = mapped_column(default=False)
    outcome: Mapped[str | None] = mapped_column(Text)
