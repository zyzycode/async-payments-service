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
    """Обрабатывает платеж, полученный consumer-ом из очереди.

    Use case выполняет основную бизнес-логику обработки:
    вызывает платежный шлюз, обновляет статус платежа и отправляет webhook.
    Если платеж уже имеет финальный статус, gateway повторно не вызывается,
    а повторяется только webhook.

    Транзакции:
        Платеж читается в короткой transaction boundary, затем gateway вызывается
        вне транзакции БД, чтобы не держать соединение 2-5 секунд. После ответа
        gateway итоговый статус сохраняется в отдельной transaction boundary.
        Webhook отправляется уже после фиксации статуса. Если webhook исчерпал
        retry и выбросил ошибку, статус платежа остается финальным, а повторная
        доставка сообщения повторит только webhook.

    Ошибки:
        `PaymentNotFoundError` или ошибка webhook/gateway пробрасывается наружу
        в consumer. Это нужно, чтобы сообщение было redelivered и после лимита
        попыток ушло в DLQ.
    """

    payment_repository: PaymentRepository
    payment_gateway: PaymentGateway
    webhook_client: WebhookClient
    transaction_manager: TransactionManager

    async def execute(self, payment_id: UUID) -> Payment:
        """Обрабатывает pending платеж или повторяет webhook для финального."""
        payment = await self._get_payment(payment_id)

        if payment.status == PaymentStatus.PENDING:
            gateway_result = await self.payment_gateway.process_payment(payment)
            payment = await self._save_gateway_result(
                payment_id=payment.id,
                status=gateway_result.status,
            )

        await self.webhook_client.send_payment_webhook(payment)
        return payment

    async def _get_payment(self, payment_id: UUID) -> Payment:
        async with self.transaction_manager:
            payment = await self.payment_repository.get_by_id(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)
            return payment

    async def _save_gateway_result(
        self,
        payment_id: UUID,
        status: PaymentStatus,
    ) -> Payment:
        async with self.transaction_manager:
            fresh_payment = await self.payment_repository.get_by_id(payment_id)
            if fresh_payment is None:
                raise PaymentNotFoundError(payment_id)

            if fresh_payment.status != PaymentStatus.PENDING:
                return fresh_payment

            return await self.payment_repository.update_status(
                payment_id=fresh_payment.id,
                status=status,
            )
