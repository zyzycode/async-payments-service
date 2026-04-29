from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.payment_repository import PaymentRepository
from app.application.ports.transaction_manager import TransactionManager
from app.application.ports.types import OutboxEventCreateData, PaymentCreateData
from app.domain.payments.entities import Currency, Payment


@dataclass(frozen=True, slots=True)
class CreatePaymentCommand:
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str


@dataclass(slots=True)
class CreatePaymentUseCase:
    payment_repository: PaymentRepository
    outbox_repository: OutboxRepository
    transaction_manager: TransactionManager
    payment_exchange: str
    payment_new_routing_key: str

    async def execute(self, command: CreatePaymentCommand) -> Payment:
        async with self.transaction_manager:
            existing_payment = await self.payment_repository.get_by_idempotency_key(
                command.idempotency_key,
            )
            if existing_payment is not None:
                return existing_payment

            payment = await self.payment_repository.create(
                PaymentCreateData(
                    amount=command.amount,
                    currency=command.currency,
                    description=command.description,
                    metadata=command.metadata,
                    webhook_url=command.webhook_url,
                    idempotency_key=command.idempotency_key,
                ),
            )
            await self.outbox_repository.create_event(
                OutboxEventCreateData(
                    exchange=self.payment_exchange,
                    routing_key=self.payment_new_routing_key,
                    payload=self._build_payment_created_payload(payment),
                ),
            )
            return payment

    @staticmethod
    def _build_payment_created_payload(payment: Payment) -> dict[str, Any]:
        return {"payment_id": str(payment.id)}
