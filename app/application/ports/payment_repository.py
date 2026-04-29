from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.ports.types import PaymentCreateData
from app.domain.payments.entities import Payment, PaymentStatus


class PaymentRepository(Protocol):
    async def create(self, data: PaymentCreateData) -> Payment:
        raise NotImplementedError

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        raise NotImplementedError

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        raise NotImplementedError

    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        processed_at: datetime | None = None,
    ) -> Payment:
        raise NotImplementedError
