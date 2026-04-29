from decimal import Decimal

import pytest

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


@pytest.mark.asyncio
async def test_create_payment_creates_payment_and_outbox_event_in_one_transaction() -> None:
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    use_case = CreatePaymentUseCase(
        payment_repository=payment_repository,
        outbox_repository=outbox_repository,
        transaction_manager=transaction_manager,
        payment_exchange=PAYMENT_EXCHANGE,
        payment_new_routing_key=PAYMENT_NEW_ROUTING_KEY,
    )

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
    use_case = CreatePaymentUseCase(
        payment_repository=payment_repository,
        outbox_repository=outbox_repository,
        transaction_manager=transaction_manager,
        payment_exchange=PAYMENT_EXCHANGE,
        payment_new_routing_key=PAYMENT_NEW_ROUTING_KEY,
    )
    command = create_command(idempotency_key="idem-repeat")

    first_payment = await use_case.execute(command)
    second_payment = await use_case.execute(command)

    assert second_payment.id == first_payment.id
    assert len(outbox_repository.events) == 1


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
