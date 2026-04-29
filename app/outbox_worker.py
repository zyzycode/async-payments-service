import asyncio

from faststream.rabbit import RabbitBroker

from app.adapters.out_db.database import async_session_factory
from app.adapters.out_db.outbox_repository import SqlAlchemyOutboxRepository
from app.adapters.out_db.transaction_manager import SqlAlchemyTransactionManager
from app.adapters.out_rabbitmq.publisher import RabbitMessagePublisher
from app.application.use_cases import OutboxPublisherUseCase
from app.core.logging import configure_logging
from app.core.settings import settings


async def run() -> None:
    """Запускает бесконечный цикл публикации outbox events.

    Worker подключается к RabbitMQ, создает SQLAlchemy session и запускает
    `OutboxPublisherUseCase`. Он нужен для гарантированной доставки событий:
    если API сохранил payment и outbox event, но публикация в RabbitMQ не
    произошла сразу, этот процесс повторно прочитает pending event и отправит
    его в брокер.
    """
    configure_logging()
    broker = RabbitBroker(settings.rabbitmq_url)
    async with broker:
        async with async_session_factory() as session:
            use_case = OutboxPublisherUseCase(
                outbox_repository=SqlAlchemyOutboxRepository(session),
                message_publisher=RabbitMessagePublisher(broker),
                transaction_manager=SqlAlchemyTransactionManager(session),
                poll_interval_seconds=settings.outbox_poll_interval_seconds,
            )
            await use_case.run_forever()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
