from uuid import UUID

import httpx
import pytest

from app.adapters.in_api.dependencies import (
    get_create_payment_use_case,
    get_get_payment_use_case,
)
from app.application.use_cases.create_payment import CreatePaymentUseCase
from app.application.use_cases.get_payment import GetPaymentUseCase
from app.application.use_cases.outbox_publisher import OutboxPublisherUseCase
from app.application.use_cases.process_payment import ProcessPaymentUseCase
from app.domain.payments.entities import PaymentStatus
from app.main import app
from tests.fakes import (
    FakeMessagePublisher,
    FakePaymentGateway,
    FakeTransactionManager,
    FakeWebhookClient,
    InMemoryOutboxRepository,
    InMemoryPaymentRepository,
)

PAYMENT_EXCHANGE = "payments"
PAYMENT_NEW_ROUTING_KEY = "payments.new"


@pytest.mark.asyncio
async def test_payment_happy_path_from_post_to_webhook() -> None:
    transaction_manager = FakeTransactionManager()
    payment_repository = InMemoryPaymentRepository(transaction_manager)
    outbox_repository = InMemoryOutboxRepository(transaction_manager)
    message_publisher = FakeMessagePublisher()
    gateway = FakePaymentGateway(status=PaymentStatus.SUCCEEDED)
    webhook_client = FakeWebhookClient()

    async def create_payment_dependency():
        yield CreatePaymentUseCase(
            payment_repository=payment_repository,
            outbox_repository=outbox_repository,
            transaction_manager=transaction_manager,
            payment_exchange=PAYMENT_EXCHANGE,
            payment_new_routing_key=PAYMENT_NEW_ROUTING_KEY,
        )

    async def get_payment_dependency():
        yield GetPaymentUseCase(
            payment_repository=payment_repository,
            transaction_manager=transaction_manager,
        )

    app.dependency_overrides[get_create_payment_use_case] = create_payment_dependency
    app.dependency_overrides[get_get_payment_use_case] = get_payment_dependency

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/payments",
                headers={
                    "X-API-Key": "test-api-key",
                    "Idempotency-Key": "idem-happy-path",
                },
                json={
                    "amount": "100.50",
                    "currency": "RUB",
                    "description": "Demo payment",
                    "metadata": {"order_id": "order-001"},
                    "webhook_url": "https://example.com/webhook",
                },
            )

        assert create_response.status_code == 202
        payment_id = UUID(create_response.json()["payment_id"])
        assert create_response.json()["status"] == "pending"
        assert len(outbox_repository.events) == 1

        outbox_use_case = OutboxPublisherUseCase(
            outbox_repository=outbox_repository,
            message_publisher=message_publisher,
            transaction_manager=transaction_manager,
            poll_interval_seconds=0.01,
        )
        published_count = await outbox_use_case.publish_pending_once()

        assert published_count == 1
        assert message_publisher.messages == [
            {
                "exchange": PAYMENT_EXCHANGE,
                "routing_key": PAYMENT_NEW_ROUTING_KEY,
                "message": {"payment_id": str(payment_id)},
            },
        ]

        process_use_case = ProcessPaymentUseCase(
            payment_repository=payment_repository,
            payment_gateway=gateway,
            webhook_client=webhook_client,
            transaction_manager=transaction_manager,
        )
        await process_use_case.execute(payment_id)

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            get_response = await client.get(
                f"/api/v1/payments/{payment_id}",
                headers={"X-API-Key": "test-api-key"},
            )

        assert get_response.status_code == 200
        assert get_response.json()["status"] == "succeeded"
        assert gateway.calls == 1
        assert webhook_client.calls == 1
    finally:
        app.dependency_overrides.clear()
