from app.application.ports.payment_gateway import PaymentGateway
from app.domain.payments.entities import Payment


class HttpPaymentGateway(PaymentGateway):
    async def charge(self, payment: Payment) -> None:
        raise NotImplementedError
