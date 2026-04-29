from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.out_db.models import OutboxModel
from app.adapters.out_db.transaction_boundary import ensure_application_transaction
from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.types import (
    OutboxEvent,
    OutboxEventCreateData,
    OutboxEventStatus,
)


def outbox_event_to_domain(model: OutboxModel) -> OutboxEvent:
    return OutboxEvent(
        id=model.id,
        exchange=model.exchange,
        routing_key=model.routing_key,
        payload=model.payload,
        status=OutboxEventStatus(model.status),
        created_at=model.created_at,
        published_at=model.published_at,
        failed_at=model.failed_at,
        next_retry_at=model.next_retry_at,
        attempts=model.attempts,
        last_error=model.last_error,
    )


class SqlAlchemyOutboxRepository(OutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_event(self, data: OutboxEventCreateData) -> OutboxEvent:
        ensure_application_transaction(self._session)
        model = OutboxModel(
            id=uuid4(),
            exchange=data.exchange,
            routing_key=data.routing_key,
            payload=data.payload,
            status=OutboxEventStatus.PENDING.value,
            attempts=0,
            last_error=None,
            created_at=datetime.now(timezone.utc),
            published_at=None,
            failed_at=None,
            next_retry_at=None,
        )
        self._session.add(model)
        await self._session.flush()
        return outbox_event_to_domain(model)

    async def get_pending_events(
        self,
        limit: int,
        now: datetime | None = None,
    ) -> list[OutboxEvent]:
        ensure_application_transaction(self._session)
        now = now or datetime.now(timezone.utc)
        result = await self._session.execute(
            select(OutboxModel)
            .where(
                OutboxModel.status == OutboxEventStatus.PENDING.value,
                or_(
                    OutboxModel.next_retry_at.is_(None),
                    OutboxModel.next_retry_at <= now,
                ),
            )
            .order_by(OutboxModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True),
        )
        return [outbox_event_to_domain(model) for model in result.scalars().all()]

    async def mark_as_published(self, event_id: UUID) -> None:
        ensure_application_transaction(self._session)
        model = await self._session.get(OutboxModel, event_id)
        if model is None:
            raise ValueError(f"Outbox event {event_id} not found")

        model.status = OutboxEventStatus.PUBLISHED.value
        model.published_at = datetime.now(timezone.utc)
        model.failed_at = None
        model.next_retry_at = None
        await self._session.flush()

    async def mark_as_failed(
        self,
        event_id: UUID,
        error: str,
        next_retry_at: datetime | None = None,
    ) -> None:
        ensure_application_transaction(self._session)
        model = await self._session.get(OutboxModel, event_id)
        if model is None:
            raise ValueError(f"Outbox event {event_id} not found")

        model.attempts += 1
        model.last_error = error
        model.failed_at = datetime.now(timezone.utc)
        model.next_retry_at = next_retry_at
        if next_retry_at is None:
            model.status = OutboxEventStatus.FAILED.value
        else:
            model.status = OutboxEventStatus.PENDING.value
        await self._session.flush()
