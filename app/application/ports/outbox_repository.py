from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.ports.types import OutboxEvent, OutboxEventCreateData


class OutboxRepository(Protocol):
    async def create_event(self, data: OutboxEventCreateData) -> OutboxEvent:
        raise NotImplementedError

    async def get_pending_events(
        self,
        limit: int,
        now: datetime | None = None,
    ) -> list[OutboxEvent]:
        raise NotImplementedError

    async def mark_as_published(self, event_id: UUID) -> None:
        raise NotImplementedError

    async def mark_as_failed(
        self,
        event_id: UUID,
        error: str,
        next_retry_at: datetime | None = None,
    ) -> None:
        raise NotImplementedError
