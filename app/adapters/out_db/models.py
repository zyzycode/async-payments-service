from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.adapters.out_db.base import Base


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_idempotency_key", "idempotency_key", unique=True),
        Index("ix_payments_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2))
    currency: Mapped[str] = mapped_column(String(length=3))
    description: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB)
    status: Mapped[str] = mapped_column(String(length=32))
    idempotency_key: Mapped[str] = mapped_column(String(length=255))
    webhook_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxModel(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_status_next_retry_at", "status", "next_retry_at"),
        Index("ix_outbox_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(length=255))
    routing_key: Mapped[str] = mapped_column(String(length=255))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(length=32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
