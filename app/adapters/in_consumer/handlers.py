from faststream.rabbit import RabbitBroker

from app.adapters.in_consumer.schemas import PaymentNewMessage
from app.adapters.in_consumer.topology import payment_exchange, payment_new_queue
from app.adapters.out_db.database import async_session_factory
from app.adapters.out_db.payment_repository import SqlAlchemyPaymentRepository
from app.adapters.out_db.transaction_manager import SqlAlchemyTransactionManager
from app.adapters.out_http.payment_gateway import HttpPaymentGateway
from app.adapters.out_http.webhook_client import HttpxWebhookClient
from app.application.use_cases import ProcessPaymentUseCase


def register_handlers(broker: RabbitBroker) -> None:
    """Регистрирует единственный consumer обработки платежей.

    Consumer читает сообщения из очереди `payments.new` и делегирует обработку
    `ProcessPaymentUseCase`. Один обработчик выполняет весь сценарий:
    эмуляцию платежного шлюза, обновление статуса в БД и отправку webhook.

    Retry и DLQ:
        `retry=True` заставляет FastStream пробросить ошибку обратно в RabbitMQ.
        Очередь `payments.new` настроена как quorum queue с dead-letter exchange.
        После 3 неуспешных попыток обработки сообщение попадает в DLQ.
    """

    @broker.subscriber(
        payment_new_queue(),
        payment_exchange(),
        retry=True,
    )
    async def process_payment(message: PaymentNewMessage) -> None:
        """Обрабатывает сообщение о новом платеже.

        Args:
            message: Сообщение `{payment_id}` из очереди `payments.new`.

        Processing:
            1. Находит платеж по `payment_id`.
            2. Если платеж уже не `pending`, завершает обработку без повторного
               вызова шлюза и webhook.
            3. Вызывает эмулятор платежного шлюза: задержка 2-5 секунд,
               вероятность успеха 90%, вероятность отказа 10%.
            4. Обновляет статус платежа в БД.
            5. Отправляет webhook клиенту.

        Ошибки:
            Если gateway, БД или webhook завершаются ошибкой, исключение
            пробрасывается наружу. RabbitMQ выполняет повторную доставку, а
            после 3 неуспешных попыток отправляет сообщение в DLQ.
        """
        async with async_session_factory() as session:
            use_case = ProcessPaymentUseCase(
                payment_repository=SqlAlchemyPaymentRepository(session),
                payment_gateway=HttpPaymentGateway(),
                webhook_client=HttpxWebhookClient(),
                transaction_manager=SqlAlchemyTransactionManager(session),
            )
            await use_case.execute(message.payment_id)
