from decimal import Decimal

import pytest

from app.application.errors import (
    DuplicateIdempotencyKeyError,
    IdempotencyConflictError,
    PaymentNotFoundError,
)
from app.application.ports.types import OutboxEventCreateData
from app.application.use_cases.create_payment import (
    CreatePaymentCommand,
    CreatePaymentUseCase,
)
from app.application.use_cases.get_payment import GetPaymentUseCase
from app.application.use_cases.outbox_publisher import OutboxPublisherUseCase
from app.application.use_cases.process_payment import ProcessPaymentUseCase
from app.domain.payments.entities import Currency, PaymentStatus
from tests.fakes import (
    FakeMessagePublisher,
    FakePaymentGateway,
    FakeTransactionManager,
    FakeWebhookClient,
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
    make_payment,
)

PAYMENT_EXCHANGE = "payments"
PAYMENT_NEW_ROUTING_KEY = "payments.new"


def create_command(idempotency_key: str = "idem-001") -> CreatePaymentCommand:
    return CreatePaymentCommand(
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Demo payment",
        metadata={"order_id": "order-001"},
        webhook_url="https://example.com/webhook",
        idempotency_key=idempotency_key,
    )


def create_use_case(
    payment_repository: InMemoryPaymentRepository,
    outbox_repository: InMemoryOutboxRepository,
    transaction_manager: FakeTransactionManager,
) -> CreatePaymentUseCase:
    return CreatePaymentUseCase(
        payment_repository=payment_repository,
        outbox_repository=outbox_repository,
        transaction_manager=transaction_manager,
        payment_exchange=PAYMENT_EXCHANGE,
        payment_new_routing_key=PAYMENT_NEW_ROUTING_KEY,
    )


def create_outbox_event_data(payload: dict) -> OutboxEventCreateData:
    return OutboxEventCreateData(
        exchange=PAYMENT_EXCHANGE,
        routing_key=PAYMENT_NEW_ROUTING_KEY,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_create_payment_creates_payment_and_outbox_event_in_one_transaction() -> None:
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    use_case = create_use_case(payment_repository, outbox_repository, transaction_manager)

    payment = await use_case.execute(create_command())

    assert payment.status == PaymentStatus.PENDING
    assert payment_repository.create_called_inside_transaction is True
    assert outbox_repository.create_called_inside_transaction is True
    assert transaction_manager.commits == 1
    assert len(outbox_repository.events) == 1

    event = outbox_repository.events[0]
    assert event.exchange == PAYMENT_EXCHANGE
    assert event.routing_key == PAYMENT_NEW_ROUTING_KEY
    assert event.payload == {"payment_id": str(payment.id)}


@pytest.mark.asyncio
async def test_create_payment_with_existing_idempotency_key_returns_existing_payment() -> None:
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    use_case = create_use_case(payment_repository, outbox_repository, transaction_manager)
    command = create_command(idempotency_key="idem-repeat")

    first_payment = await use_case.execute(command)
    second_payment = await use_case.execute(command)

    assert second_payment.id == first_payment.id
    assert len(outbox_repository.events) == 1


@pytest.mark.asyncio
async def test_create_payment_rejects_same_idempotency_key_with_different_payload() -> None:
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    use_case = create_use_case(payment_repository, outbox_repository, transaction_manager)

    await use_case.execute(create_command(idempotency_key="idem-conflict"))
    changed_command = create_command(idempotency_key="idem-conflict")
    changed_command = CreatePaymentCommand(
        amount=Decimal("200.00"),
        currency=changed_command.currency,
        description=changed_command.description,
        metadata=changed_command.metadata,
        webhook_url=changed_command.webhook_url,
        idempotency_key=changed_command.idempotency_key,
    )

    with pytest.raises(IdempotencyConflictError):
        await use_case.execute(changed_command)


class RacePaymentRepository(InMemoryPaymentRepository):
    def __init__(
        self,
        transaction_manager: FakeTransactionManager,
        existing_payment_idempotency_key: str,
    ) -> None:
        super().__init__(transaction_manager)
        self._hidden_payment = None
        self._first_lookup = True
        self._existing_payment_idempotency_key = existing_payment_idempotency_key

    async def create(self, data):
        self._hidden_payment = make_payment(
            idempotency_key=self._existing_payment_idempotency_key,
            request_hash=data.request_hash,
        )
        self.add(self._hidden_payment)
        raise DuplicateIdempotencyKeyError(data.idempotency_key)

    async def get_by_idempotency_key(self, idempotency_key: str):
        if self._first_lookup:
            self._first_lookup = False
            return None
        return await super().get_by_idempotency_key(idempotency_key)


@pytest.mark.asyncio
async def test_create_payment_returns_existing_after_concurrent_unique_conflict() -> None:
    transaction_manager = FakeTransactionManager()
    payment_repository = RacePaymentRepository(transaction_manager, "idem-race")
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    use_case = create_use_case(payment_repository, outbox_repository, transaction_manager)

    payment = await use_case.execute(create_command(idempotency_key="idem-race"))

    assert payment.id == payment_repository._hidden_payment.id
    assert len(outbox_repository.events) == 0


@pytest.mark.asyncio
async def test_get_payment_returns_existing_payment() -> None:
    payment = make_payment()
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    payment_repository.add(payment)
    use_case = GetPaymentUseCase(
        payment_repository=payment_repository,
        transaction_manager=transaction_manager,
    )

    result = await use_case.execute(payment.id)

    assert result.id == payment.id
    assert transaction_manager.commits == 1


@pytest.mark.asyncio
async def test_get_payment_raises_when_payment_not_found() -> None:
    payment = make_payment()
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    use_case = GetPaymentUseCase(
        payment_repository=payment_repository,
        transaction_manager=transaction_manager,
    )

    with pytest.raises(PaymentNotFoundError):
        await use_case.execute(payment.id)

    assert transaction_manager.rollbacks == 1


@pytest.mark.asyncio
async def test_outbox_publisher_publishes_pending_event_and_marks_it_published() -> None:
    transaction_manager = FakeTransactionManager()
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    publisher = FakeMessagePublisher()
    use_case = OutboxPublisherUseCase(
        outbox_repository=outbox_repository,
        message_publisher=publisher,
        transaction_manager=transaction_manager,
        poll_interval_seconds=0.01,
    )
    event = await outbox_repository.create_event(
        data=create_outbox_event_data(payload={"payment_id": "payment-001"}),
    )

    processed_count = await use_case.publish_pending_once()

    stored_event = outbox_repository.events[0]
    assert processed_count == 1
    assert publisher.messages == [
        {
            "exchange": PAYMENT_EXCHANGE,
            "routing_key": PAYMENT_NEW_ROUTING_KEY,
            "message": {"payment_id": "payment-001"},
        },
    ]
    assert stored_event.id == event.id
    assert stored_event.status.value == "published"
    assert stored_event.published_at is not None


@pytest.mark.asyncio
async def test_outbox_publisher_schedules_retry_when_publish_fails() -> None:
    transaction_manager = FakeTransactionManager()
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    publisher = FakeMessagePublisher(exc=RuntimeError("rabbit is down"))
    use_case = OutboxPublisherUseCase(
        outbox_repository=outbox_repository,
        message_publisher=publisher,
        transaction_manager=transaction_manager,
        poll_interval_seconds=0.01,
    )
    await outbox_repository.create_event(
        data=create_outbox_event_data(payload={"payment_id": "payment-001"}),
    )

    processed_count = await use_case.publish_pending_once()

    stored_event = outbox_repository.events[0]
    assert processed_count == 1
    assert stored_event.status.value == "pending"
    assert stored_event.attempts == 1
    assert stored_event.last_error == "rabbit is down"
    assert stored_event.next_retry_at is not None


@pytest.mark.asyncio
async def test_outbox_publisher_marks_event_failed_after_max_attempts() -> None:
    transaction_manager = FakeTransactionManager()
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    publisher = FakeMessagePublisher(exc=RuntimeError("rabbit is down"))
    use_case = OutboxPublisherUseCase(
        outbox_repository=outbox_repository,
        message_publisher=publisher,
        transaction_manager=transaction_manager,
        poll_interval_seconds=0.01,
        max_attempts=1,
    )
    await outbox_repository.create_event(
        data=create_outbox_event_data(payload={"payment_id": "payment-001"}),
    )

    processed_count = await use_case.publish_pending_once()

    stored_event = outbox_repository.events[0]
    assert processed_count == 1
    assert stored_event.status.value == "failed"
    assert stored_event.attempts == 1
    assert stored_event.last_error == "rabbit is down"
    assert stored_event.next_retry_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED])
async def test_process_payment_retries_webhook_for_finished_payment_without_gateway(
    status: PaymentStatus,
) -> None:
    payment = make_payment(status=status)
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    payment_repository.add(payment)
    gateway = FakePaymentGateway()
    webhook_client = FakeWebhookClient()
    use_case = ProcessPaymentUseCase(
        payment_repository=payment_repository,
        payment_gateway=gateway,
        webhook_client=webhook_client,
        transaction_manager=transaction_manager,
    )

    result = await use_case.execute(payment.id)

    assert result.id == payment.id
    assert result.status == status
    assert gateway.calls == 0
    assert webhook_client.calls == 1
    assert payment_repository.update_calls == 0


@pytest.mark.asyncio
async def test_process_payment_updates_pending_payment_before_webhook() -> None:
    payment = make_payment(status=PaymentStatus.PENDING)
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    payment_repository.add(payment)
    gateway = FakePaymentGateway(status=PaymentStatus.SUCCEEDED)
    webhook_client = FakeWebhookClient()
    use_case = ProcessPaymentUseCase(
        payment_repository=payment_repository,
        payment_gateway=gateway,
        webhook_client=webhook_client,
        transaction_manager=transaction_manager,
    )

    result = await use_case.execute(payment.id)

    assert result.id == payment.id
    assert result.status == PaymentStatus.SUCCEEDED
    assert result.processed_at is not None
    assert gateway.calls == 1
    assert webhook_client.calls == 1
    assert payment_repository.update_calls == 1


@pytest.mark.asyncio
async def test_process_payment_keeps_final_status_when_webhook_fails() -> None:
    payment = make_payment(status=PaymentStatus.PENDING)
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    payment_repository.add(payment)
    gateway = FakePaymentGateway(status=PaymentStatus.SUCCEEDED)
    webhook_client = FakeWebhookClient(exc=RuntimeError("webhook failed"))
    use_case = ProcessPaymentUseCase(
        payment_repository=payment_repository,
        payment_gateway=gateway,
        webhook_client=webhook_client,
        transaction_manager=transaction_manager,
    )

    with pytest.raises(RuntimeError, match="webhook failed"):
        await use_case.execute(payment.id)

    stored_payment = await payment_repository.get_by_id(payment.id)
    assert stored_payment is not None
    assert stored_payment.status == PaymentStatus.SUCCEEDED
    assert stored_payment.processed_at is not None
    assert gateway.calls == 1
    assert webhook_client.calls == 1
    assert payment_repository.update_calls == 1
