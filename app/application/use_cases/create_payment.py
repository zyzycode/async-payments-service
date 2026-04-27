from dataclasses import dataclass

from app.application.ports.payment_events import PaymentEventPublisher
from app.application.ports.payment_repository import PaymentRepository


@dataclass(slots=True)
class CreatePaymentUseCase:
    payment_repository: PaymentRepository
    event_publisher: PaymentEventPublisher

    async def execute(self) -> None:
        raise NotImplementedError("Payment creation flow is not implemented yet.")
