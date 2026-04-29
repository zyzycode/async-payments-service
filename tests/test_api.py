from uuid import UUID, uuid4

import httpx
import pytest

from app.adapters.in_api.dependencies import (
    get_create_payment_use_case,
    get_get_payment_use_case,
)
from app.application.errors import PaymentNotFoundError
from app.domain.payments.entities import Payment
from app.main import app
from tests.fakes import make_payment


class FakeCreatePaymentUseCase:
    def __init__(self) -> None:
        self.payments_by_idempotency_key: dict[str, Payment] = {}

    async def execute(self, command) -> Payment:
        existing = self.payments_by_idempotency_key.get(command.idempotency_key)
        if existing is not None:
            return existing

        payment = make_payment(idempotency_key=command.idempotency_key)
        self.payments_by_idempotency_key[command.idempotency_key] = payment
        return payment


class FakeGetPaymentUseCase:
    def __init__(self, payments: dict[UUID, Payment]) -> None:
        self.payments = payments

    async def execute(self, payment_id: UUID) -> Payment:
        payment = self.payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment


def create_payment_dependency(fake_use_case: FakeCreatePaymentUseCase):
    async def dependency():
        yield fake_use_case

    return dependency


def get_payment_dependency(fake_use_case: FakeGetPaymentUseCase):
    async def dependency():
        yield fake_use_case

    return dependency


@pytest.mark.asyncio
async def test_create_payment_returns_accepted() -> None:
    fake_use_case = FakeCreatePaymentUseCase()
    app.dependency_overrides[get_create_payment_use_case] = create_payment_dependency(fake_use_case)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/payments",
            headers={
                "X-API-Key": "test-api-key",
                "Idempotency-Key": "idem-001",
            },
            json={
                "amount": "100.50",
                "currency": "RUB",
                "description": "Demo payment",
                "metadata": {"order_id": "order-001"},
                "webhook_url": "https://example.com/webhook",
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert UUID(body["payment_id"])
    assert body["created_at"]


@pytest.mark.asyncio
async def test_repeated_post_with_same_idempotency_key_returns_same_payment() -> None:
    fake_use_case = FakeCreatePaymentUseCase()
    app.dependency_overrides[get_create_payment_use_case] = create_payment_dependency(fake_use_case)

    request = {
        "amount": "100.50",
        "currency": "RUB",
        "description": "Demo payment",
        "metadata": {"order_id": "order-001"},
        "webhook_url": "https://example.com/webhook",
    }
    headers = {
        "X-API-Key": "test-api-key",
        "Idempotency-Key": "idem-duplicate",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_response = await client.post("/api/v1/payments", headers=headers, json=request)
        second_response = await client.post("/api/v1/payments", headers=headers, json=request)

    app.dependency_overrides.clear()

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert first_response.json()["payment_id"] == second_response.json()["payment_id"]


@pytest.mark.asyncio
async def test_get_payment_returns_payment_details() -> None:
    payment = make_payment(payment_id=uuid4())
    fake_use_case = FakeGetPaymentUseCase({payment.id: payment})
    app.dependency_overrides[get_get_payment_use_case] = get_payment_dependency(fake_use_case)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/payments/{payment.id}",
            headers={"X-API-Key": "test-api-key"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(payment.id)
    assert body["amount"] == "100.50"
    assert body["currency"] == "RUB"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_get_unknown_payment_returns_404() -> None:
    app.dependency_overrides[get_get_payment_use_case] = get_payment_dependency(FakeGetPaymentUseCase({}))
    payment_id = uuid4()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"X-API-Key": "test-api-key"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert str(payment_id) in response.json()["detail"]


@pytest.mark.asyncio
async def test_x_api_key_is_required() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/payments/{uuid4()}")

    assert response.status_code == 401
