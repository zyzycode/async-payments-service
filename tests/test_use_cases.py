from decimal import Decimal

import pytest

from app.application.errors import (
    DuplicateIdempotencyKeyError,
    IdempotencyConflictError,
)
from app.application.use_cases.create_payment import (
    CreatePaymentCommand,
    CreatePaymentUseCase,
)
from app.application.use_cases.process_payment import ProcessPaymentUseCase
from app.domain.payments.entities import Currency, PaymentStatus
from tests.fakes import (
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
@pytest.mark.parametrize("status", [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED])
async def test_process_payment_does_not_process_finished_payment_again(status: PaymentStatus) -> None:
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
    assert webhook_client.calls == 0
    assert payment_repository.update_calls == 0
