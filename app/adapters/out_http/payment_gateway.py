import asyncio
import random
from uuid import uuid4

from app.application.ports.payment_gateway import PaymentGateway
from app.application.ports.types import GatewayPaymentResult
from app.domain.payments.entities import Payment, PaymentStatus


class HttpPaymentGateway(PaymentGateway):
    """Эмулирует работу внешнего платежного шлюза.

    Адаптер не выполняет реальные HTTP-запросы. Он имитирует задержку сети и
    провайдера, после чего возвращает случайный результат платежа:
    90% вызовов завершаются статусом `succeeded`, 10% — статусом `failed`.

    Реализация относится к outbound HTTP adapter layer и реализует application
    port `PaymentGateway`.
    """

    async def process_payment(self, payment: Payment) -> GatewayPaymentResult:
        """Обрабатывает платеж через эмулированный шлюз.

        Args:
            payment: Доменная сущность платежа, которую нужно обработать.

        Returns:
            GatewayPaymentResult с итоговым статусом платежа, опциональным
            идентификатором платежа у провайдера и сырым эмулированным ответом.
        """
        await asyncio.sleep(random.uniform(2, 5))

        is_successful = random.random() < 0.9
        status = PaymentStatus.SUCCEEDED if is_successful else PaymentStatus.FAILED
        provider_payment_id = str(uuid4()) if is_successful else None

        return GatewayPaymentResult(
            status=status,
            provider_payment_id=provider_payment_id,
            raw_response={
                "payment_id": str(payment.id),
                "provider_payment_id": provider_payment_id,
                "status": status.value,
            },
        )
