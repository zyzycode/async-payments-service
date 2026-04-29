from typing import Any, Protocol

from app.domain.payments.entities import Payment


class WebhookClient(Protocol):
    async def send_payment_webhook(self, payment: Payment) -> None:
        raise NotImplementedError

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError
