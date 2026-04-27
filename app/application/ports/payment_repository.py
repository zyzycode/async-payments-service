from typing import Protocol
from uuid import UUID

from app.domain.payments.entities import Payment


class PaymentRepository(Protocol):
    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        raise NotImplementedError

    async def add(self, payment: Payment) -> None:
        raise NotImplementedError
