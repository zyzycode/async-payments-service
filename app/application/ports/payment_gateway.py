from typing import Protocol

from app.application.ports.types import GatewayPaymentResult
from app.domain.payments.entities import Payment


class PaymentGateway(Protocol):
    async def process_payment(self, payment: Payment) -> GatewayPaymentResult:
        raise NotImplementedError
