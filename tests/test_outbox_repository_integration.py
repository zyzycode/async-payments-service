import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.out_db.models import OutboxModel
from app.adapters.out_db.outbox_repository import SqlAlchemyOutboxRepository
from app.adapters.out_db.transaction_manager import SqlAlchemyTransactionManager
from app.application.ports.types import OutboxEventCreateData
from app.core.settings import settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION_TESTS") != "1",
    reason="set RUN_POSTGRES_INTEGRATION_TESTS=1 to run Postgres integration tests",
)


@pytest.mark.asyncio
async def test_outbox_repository_skips_rows_locked_by_another_transaction() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autobegin=False,
    )
    event_id = None

    try:
        async with session_factory() as session:
            repository = SqlAlchemyOutboxRepository(session)
            transaction_manager = SqlAlchemyTransactionManager(session)
            async with transaction_manager:
                event = await repository.create_event(
                    OutboxEventCreateData(
                        exchange="payments",
                        routing_key="payments.new",
                        payload={"test": "skip-locked"},
                    ),
                )
                event_id = event.id
                await session.execute(
                    update(OutboxModel)
                    .where(OutboxModel.id == event.id)
                    .values(created_at=datetime(2000, 1, 1, tzinfo=timezone.utc)),
                )

        async with session_factory() as first_session, session_factory() as second_session:
            first_repository = SqlAlchemyOutboxRepository(first_session)
            first_transaction = SqlAlchemyTransactionManager(first_session)
            await first_transaction.__aenter__()

            try:
                first_events = await first_repository.get_pending_events(limit=1)
                assert first_events[0].id == event_id

                second_repository = SqlAlchemyOutboxRepository(second_session)
                second_transaction = SqlAlchemyTransactionManager(second_session)
                await second_transaction.__aenter__()

                try:
                    second_events = await second_repository.get_pending_events(limit=10)
                finally:
                    await second_transaction.__aexit__(None, None, None)

                assert event_id not in {event.id for event in second_events}
            finally:
                await first_transaction.__aexit__(None, None, None)

    finally:
        if event_id is not None:
            async with session_factory() as session:
                transaction_manager = SqlAlchemyTransactionManager(session)
                async with transaction_manager:
                    await session.execute(delete(OutboxModel).where(OutboxModel.id == event_id))
        await engine.dispose()
