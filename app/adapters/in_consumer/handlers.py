import logging

from faststream.rabbit import RabbitBroker

from app.adapters.in_consumer.schemas import PaymentNewMessage
from app.adapters.in_consumer.topology import (
    PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS,
    payment_dlx,
    payment_exchange,
    payment_new_queue,
    payment_retry_queue_configs,
)
from app.adapters.out_db.database import async_session_factory
from app.adapters.out_db.payment_repository import SqlAlchemyPaymentRepository
from app.adapters.out_db.transaction_manager import SqlAlchemyTransactionManager
from app.adapters.out_http.payment_gateway import HttpPaymentGateway
from app.adapters.out_http.webhook_client import HttpxWebhookClient
from app.application.use_cases import ProcessPaymentUseCase
from app.core.settings import settings

logger = logging.getLogger(__name__)


def register_handlers(broker: RabbitBroker) -> None:
    """Регистрирует единственный consumer обработки платежей.

    Consumer читает сообщения из очереди `payments.new` и делегирует обработку
    `ProcessPaymentUseCase`. Один обработчик выполняет весь сценарий:
    эмуляцию платежного шлюза, обновление статуса в БД и отправку webhook.

    Retry и DLQ:
        Retry обработки сообщения реализован явно через RabbitMQ retry queues с
        TTL и exponential backoff: 1 секунда перед второй попыткой и 2 секунды
        перед третьей. После 3 неуспешных попыток consumer публикует сообщение
        в DLX, откуда оно попадает в DLQ.
    """

    @broker.subscriber(
        payment_new_queue(),
        payment_exchange(),
        retry=True,
    )
    async def process_payment(message: PaymentNewMessage) -> None:
        """Обрабатывает сообщение о новом платеже.

        Args:
            message: Сообщение `{payment_id, attempt}` из очереди
                `payments.new`. Старые сообщения без `attempt` считаются первой
                попыткой.

        Processing:
            1. Находит платеж по `payment_id`.
            2. Если платеж уже не `pending`, завершает обработку без повторного
               вызова шлюза и webhook.
            3. Вызывает эмулятор платежного шлюза: задержка 2-5 секунд,
               вероятность успеха 90%, вероятность отказа 10%.
            4. Обновляет статус платежа в БД.
            5. Отправляет webhook клиенту.

        Ошибки:
            Если gateway, БД или webhook завершаются ошибкой, сообщение
            публикуется в retry queue следующей попытки. После третьей ошибки
            оно публикуется в DLX с routing key DLQ. Если публикация в retry/DLQ
            сама падает, исключение пробрасывается наружу, чтобы исходное
            сообщение не было подтверждено.
        """
        try:
            async with async_session_factory() as session:
                use_case = ProcessPaymentUseCase(
                    payment_repository=SqlAlchemyPaymentRepository(session),
                    payment_gateway=HttpPaymentGateway(),
                    webhook_client=HttpxWebhookClient(),
                    transaction_manager=SqlAlchemyTransactionManager(session),
                )
                await use_case.execute(message.payment_id)
        except Exception as exc:
            await _retry_or_dead_letter(broker, message, exc)


async def _retry_or_dead_letter(
    broker: RabbitBroker,
    message: PaymentNewMessage,
    exc: Exception,
) -> None:
    next_attempt = message.attempt + 1
    payload = {
        "payment_id": str(message.payment_id),
        "attempt": next_attempt,
        "last_error": str(exc),
    }

    if message.attempt >= PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS:
        logger.warning(
            "Payment processing failed after %s attempts, sending to DLQ: payment_id=%s",
            message.attempt,
            message.payment_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        await broker.publish(
            payload,
            exchange=payment_dlx(),
            routing_key=settings.payment_dlq,
            persist=True,
        )
        return

    retry_config = payment_retry_queue_configs()[message.attempt - 1]
    logger.warning(
        "Payment processing failed, scheduling retry attempt %s/%s in %ss: payment_id=%s",
        next_attempt,
        PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS,
        retry_config.delay_seconds,
        message.payment_id,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    await broker.publish(
        payload,
        exchange=payment_exchange(),
        routing_key=retry_config.routing_key,
        persist=True,
    )
