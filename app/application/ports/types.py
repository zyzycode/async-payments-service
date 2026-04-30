from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from app.domain.payments.entities import Currency, PaymentStatus


@dataclass(frozen=True, slots=True)
class PaymentCreateData:
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    idempotency_key: str
    request_hash: str
    webhook_url: str


class OutboxEventStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OutboxEventCreateData:
    exchange: str
    routing_key: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    exchange: str
    routing_key: str
    payload: dict[str, Any]
    status: OutboxEventStatus
    created_at: datetime
    published_at: datetime | None = None
    failed_at: datetime | None = None
    next_retry_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class GatewayPaymentResult:
    status: PaymentStatus
    provider_payment_id: str | None = None
    raw_response: dict[str, Any] | None = None
