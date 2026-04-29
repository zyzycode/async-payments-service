from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

from app.domain.payments.entities import Currency, Payment


class CreatePaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: Currency
    description: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: AnyUrl


class CreatePaymentResponse(BaseModel):
    payment_id: UUID
    status: str
    created_at: datetime

    @classmethod
    def from_domain(cls, payment: Payment) -> "CreatePaymentResponse":
        return cls(
            payment_id=payment.id,
            status=payment.status.value,
            created_at=payment.created_at,
        )


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: str
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_domain(cls, payment: Payment) -> "PaymentResponse":
        return cls(
            id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata,
            status=payment.status.value,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )
