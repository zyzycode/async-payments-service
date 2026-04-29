from dataclasses import dataclass
from uuid import UUID

from app.application.errors import PaymentNotFoundError
from app.application.ports.payment_gateway import PaymentGateway
from app.application.ports.payment_repository import PaymentRepository
from app.application.ports.transaction_manager import TransactionManager
from app.application.ports.webhook_client import WebhookClient
from app.domain.payments.entities import Payment, PaymentStatus


@dataclass(slots=True)
class ProcessPaymentUseCase:
    payment_repository: PaymentRepository
    payment_gateway: PaymentGateway
    webhook_client: WebhookClient
    transaction_manager: TransactionManager

    async def execute(self, payment_id: UUID) -> Payment:
        async with self.transaction_manager:
            payment = await self.payment_repository.get_by_id(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)

            if payment.status != PaymentStatus.PENDING:
                return payment

        gateway_result = await self.payment_gateway.process_payment(payment)

        async with self.transaction_manager:
            fresh_payment = await self.payment_repository.get_by_id(payment_id)
            if fresh_payment is None:
                raise PaymentNotFoundError(payment_id)

            if fresh_payment.status != PaymentStatus.PENDING:
                return fresh_payment

            processed_payment = await self.payment_repository.update_status(
                payment_id=fresh_payment.id,
                status=gateway_result.status,
            )
            await self.webhook_client.send_payment_webhook(processed_payment)
            return processed_payment
