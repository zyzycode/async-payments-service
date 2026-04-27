from typing import Protocol

from app.domain.payments.entities import Payment


class PaymentEventPublisher(Protocol):
    async def publish_payment_created(self, payment: Payment) -> None:
        raise NotImplementedError
