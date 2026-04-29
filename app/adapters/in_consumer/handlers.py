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
    @broker.subscriber(
        payment_new_queue(),
        payment_exchange(),
        retry=True,
    )
    async def process_payment(message: PaymentNewMessage) -> None:
        async with async_session_factory() as session:
            use_case = ProcessPaymentUseCase(
                payment_repository=SqlAlchemyPaymentRepository(session),
                payment_gateway=HttpPaymentGateway(),
                webhook_client=HttpxWebhookClient(),
                transaction_manager=SqlAlchemyTransactionManager(session),
            )
            await use_case.execute(message.payment_id)
