from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.application.ports.types import (
    GatewayPaymentResult,
    OutboxEvent,
    OutboxEventCreateData,
    OutboxEventStatus,
    PaymentCreateData,
)
from app.domain.payments.entities import Currency, Payment, PaymentStatus


def make_payment(
    payment_id: UUID | None = None,
    status: PaymentStatus = PaymentStatus.PENDING,
    idempotency_key: str = "idem-key",
    request_hash: str = "request-hash",
) -> Payment:
    return Payment(
        id=payment_id or uuid4(),
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Demo payment",
        metadata={"order_id": "order-001"},
        status=status,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        webhook_url="https://example.com/webhook",
        created_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc) if status != PaymentStatus.PENDING else None,
    )


class FakeTransactionManager:
    def __init__(self) -> None:
        self.active = False
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> "FakeTransactionManager":
        self.active = True
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if exc_type is None:
            await self.commit()
        else:
            await self.rollback()
        self.active = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class InMemoryPaymentRepository:
    def __init__(self, transaction_manager: FakeTransactionManager | None = None) -> None:
        self._payments: dict[UUID, Payment] = {}
        self._idempotency_index: dict[str, UUID] = {}
        self.transaction_manager = transaction_manager
        self.create_called_inside_transaction = False
        self.update_calls = 0

    async def create(self, data: PaymentCreateData) -> Payment:
        self.create_called_inside_transaction = self._is_transaction_active()
        payment = Payment(
            id=uuid4(),
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            metadata=data.metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=data.idempotency_key,
            request_hash=data.request_hash,
            webhook_url=data.webhook_url,
            created_at=datetime.now(timezone.utc),
            processed_at=None,
        )
        self._payments[payment.id] = payment
        self._idempotency_index[payment.idempotency_key] = payment.id
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        return self._payments.get(payment_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        payment_id = self._idempotency_index.get(idempotency_key)
        if payment_id is None:
            return None
        return self._payments[payment_id]

    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        processed_at: datetime | None = None,
    ) -> Payment:
        self.update_calls += 1
        payment = self._payments[payment_id]
        payment.status = status
        payment.processed_at = processed_at or datetime.now(timezone.utc)
        return payment

    def add(self, payment: Payment) -> None:
        self._payments[payment.id] = payment
        self._idempotency_index[payment.idempotency_key] = payment.id

    def _is_transaction_active(self) -> bool:
        return self.transaction_manager.active if self.transaction_manager else False


class InMemoryOutboxRepository:
    def __init__(self, transaction_manager: FakeTransactionManager | None = None) -> None:
        self.events: list[OutboxEvent] = []
        self.transaction_manager = transaction_manager
        self.create_called_inside_transaction = False

    async def create_event(self, data: OutboxEventCreateData) -> OutboxEvent:
        self.create_called_inside_transaction = self._is_transaction_active()
        event = OutboxEvent(
            id=uuid4(),
            exchange=data.exchange,
            routing_key=data.routing_key,
            payload=data.payload,
            status=OutboxEventStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        self.events.append(event)
        return event

    async def get_pending_events(self, limit: int, now: datetime | None = None) -> list[OutboxEvent]:
        return self.events[:limit]

    async def mark_as_published(self, event_id: UUID) -> None:
        return None

    async def mark_as_failed(
        self,
        event_id: UUID,
        error: str,
        next_retry_at: datetime | None = None,
    ) -> None:
        return None

    def _is_transaction_active(self) -> bool:
        return self.transaction_manager.active if self.transaction_manager else False


class FakePaymentGateway:
    def __init__(self, status: PaymentStatus = PaymentStatus.SUCCEEDED) -> None:
        self.status = status
        self.calls = 0

    async def process_payment(self, payment: Payment) -> GatewayPaymentResult:
        self.calls += 1
        return GatewayPaymentResult(status=self.status)


class FakeWebhookClient:
    def __init__(self) -> None:
        self.calls = 0

    async def send_payment_webhook(self, payment: Payment) -> None:
        self.calls += 1

    async def send_webhook(self, url: str, payload: dict) -> None:
        self.calls += 1
