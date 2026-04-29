import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.application.ports.message_publisher import MessagePublisher
from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.transaction_manager import TransactionManager
from app.application.ports.types import OutboxEvent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OutboxPublisherUseCase:
    outbox_repository: OutboxRepository
    message_publisher: MessagePublisher
    transaction_manager: TransactionManager
    poll_interval_seconds: float
    batch_size: int = 10
    max_attempts: int = 3
    retry_base_delay_seconds: float = 1.0

    async def run_forever(self) -> None:
        while True:
            await self.publish_pending_once()
            await asyncio.sleep(self.poll_interval_seconds)

    async def publish_pending_once(self) -> int:
        events = await self._get_pending_events()
        for event in events:
            await self._publish_event(event)
        return len(events)

    async def _get_pending_events(self) -> list[OutboxEvent]:
        async with self.transaction_manager:
            return await self.outbox_repository.get_pending_events(limit=self.batch_size)

    async def _publish_event(self, event: OutboxEvent) -> None:
        try:
            await self.message_publisher.publish(
                exchange=event.exchange,
                routing_key=event.routing_key,
                message=event.payload,
            )
        except Exception as exc:
            await self._mark_as_failed(event, exc)
            return

        async with self.transaction_manager:
            await self.outbox_repository.mark_as_published(event.id)

    async def _mark_as_failed(self, event: OutboxEvent, exc: Exception) -> None:
        next_attempt = event.attempts + 1
        next_retry_at = None
        if next_attempt < self.max_attempts:
            next_retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=self.retry_base_delay_seconds * 2 ** (next_attempt - 1),
            )

        logger.warning(
            "Failed to publish outbox event %s, attempt %s/%s",
            event.id,
            next_attempt,
            self.max_attempts,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        async with self.transaction_manager:
            await self.outbox_repository.mark_as_failed(
                event_id=event.id,
                error=str(exc),
                next_retry_at=next_retry_at,
            )
