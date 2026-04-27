from typing import Protocol

from app.domain.payments.entities import Payment


class PaymentGateway(Protocol):
    async def charge(self, payment: Payment) -> None:
        raise NotImplementedError
