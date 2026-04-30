import asyncio
from typing import Any

import httpx

from app.application.errors import WebhookDeliveryError
from app.application.ports.webhook_client import WebhookClient
from app.core.settings import settings
from app.domain.payments.entities import Payment


class HttpxWebhookClient(WebhookClient):
    """Отправляет webhook клиенту с retry и экспоненциальной задержкой.

    Адаптер реализует application port `WebhookClient` и является границей
    outbound HTTP взаимодействия. Он отправляет результат обработки платежа на
    `payment.webhook_url`.

    Retry:
        На каждый webhook выполняется до 3 попыток. Между попытками используется
        экспоненциальная задержка: 1 секунда перед второй попыткой и 2 секунды
        перед третьей. Если все попытки исчерпаны, выбрасывается
        `WebhookDeliveryError`.

    Гарантия обработки:
        `ProcessPaymentUseCase` вызывает этот адаптер после фиксации итогового
        статуса платежа в БД. Поэтому ошибка webhook пробрасывается в consumer,
        но не откатывает статус: повторная доставка сообщения повторит только
        webhook и не будет заново вызывать payment gateway.
    """

    def __init__(
        self,
        timeout_seconds: float | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._timeout_seconds = timeout_seconds or settings.webhook_timeout_seconds
        self._max_attempts = max_attempts

    async def send_payment_webhook(self, payment: Payment) -> None:
        """Отправляет webhook с результатом обработки платежа.

        Args:
            payment: Платеж с итоговым статусом и заполненным `processed_at`.

        Payload:
            `payment_id`, `status`, `amount`, `currency`, `processed_at`.

        Raises:
            WebhookDeliveryError: Если HTTP-запрос не удалось доставить после
                всех retry.
        """
        processed_at = payment.processed_at.isoformat() if payment.processed_at else None
        await self.send_webhook(
            url=payment.webhook_url,
            payload={
                "payment_id": str(payment.id),
                "status": payment.status.value,
                "amount": str(payment.amount),
                "currency": payment.currency.value,
                "processed_at": processed_at,
            },
        )

    async def send_webhook(self, url: str, payload: dict[str, Any]) -> None:
        """Выполняет HTTP POST webhook payload на указанный URL.

        Args:
            url: URL клиента, на который нужно отправить уведомление.
            payload: JSON-совместимое тело webhook.

        Raises:
            WebhookDeliveryError: Если все попытки завершились HTTP или network
                ошибкой.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    return
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))

        if last_error is None:
            last_error = RuntimeError("Webhook delivery failed")
        raise WebhookDeliveryError(
            url=url,
            attempts=self._max_attempts,
            last_error=last_error,
        )
