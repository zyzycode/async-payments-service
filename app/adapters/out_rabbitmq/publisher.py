from faststream.rabbit import RabbitBroker

from app.application.ports.payment_events import PaymentEventPublisher
from app.domain.payments.entities import Payment


class RabbitPaymentEventPublisher(PaymentEventPublisher):
    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish_payment_created(self, payment: Payment) -> None:
        raise NotImplementedError
