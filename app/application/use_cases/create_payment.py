import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.application.errors import (
    DuplicateIdempotencyKeyError,
    IdempotencyConflictError,
)
from app.application.ports.outbox_repository import OutboxRepository
from app.application.ports.payment_repository import PaymentRepository
from app.application.ports.transaction_manager import TransactionManager
from app.application.ports.types import OutboxEventCreateData, PaymentCreateData
from app.domain.payments.entities import Currency, Payment

LEGACY_REQUEST_HASH = "legacy"


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
    """Создает платеж с защитой от дублей и записью outbox event.

    Use case не зависит от FastAPI, SQLAlchemy или RabbitMQ напрямую. Все
    внешние действия выполняются через application ports.

    Идемпотентность:
        Дубликат определяется по `idempotency_key`, который хранится в таблице
        `payments` и защищен уникальным индексом. Вместе с ключом сохраняется
        `request_hash` от тела запроса. При повторном запросе с тем же ключом и
        тем же hash возвращается уже существующий платеж, а новый outbox event
        не создается. Если ключ повторно использован с другим payload,
        выбрасывается `IdempotencyConflictError`.

    Конкурентные запросы:
        Если два одинаковых запроса одновременно проходят первичную проверку,
        уникальный индекс в БД не даст создать дубль. Use case перехватывает
        конфликт, перечитывает существующий платеж и применяет обычную
        idempotency-проверку по `request_hash`.

    Outbox:
        При создании нового платежа в той же application transaction создается
        событие `payments.new` с payload `{"payment_id": ...}`. Это гарантирует,
        что платеж и событие либо сохраняются вместе, либо вместе откатываются.
    """

    payment_repository: PaymentRepository
    outbox_repository: OutboxRepository
    transaction_manager: TransactionManager
    payment_exchange: str
    payment_new_routing_key: str

    async def execute(self, command: CreatePaymentCommand) -> Payment:
        """Создает платеж или возвращает существующий по `idempotency_key`."""
        request_hash = self._build_request_hash(command)
        try:
            return await self._create_or_get_existing(command, request_hash)
        except DuplicateIdempotencyKeyError:
            return await self._get_existing_after_unique_conflict(command, request_hash)

    async def _create_or_get_existing(
        self,
        command: CreatePaymentCommand,
        request_hash: str,
    ) -> Payment:
        async with self.transaction_manager:
            existing_payment = await self.payment_repository.get_by_idempotency_key(
                command.idempotency_key,
            )
            if existing_payment is not None:
                self._ensure_same_request_hash(existing_payment, request_hash)
                return existing_payment

            payment = await self.payment_repository.create(
                PaymentCreateData(
                    amount=command.amount,
                    currency=command.currency,
                    description=command.description,
                    metadata=command.metadata,
                    webhook_url=command.webhook_url,
                    idempotency_key=command.idempotency_key,
                    request_hash=request_hash,
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

    async def _get_existing_after_unique_conflict(
        self,
        command: CreatePaymentCommand,
        request_hash: str,
    ) -> Payment:
        async with self.transaction_manager:
            existing_payment = await self.payment_repository.get_by_idempotency_key(
                command.idempotency_key,
            )
            if existing_payment is None:
                raise DuplicateIdempotencyKeyError(command.idempotency_key)
            self._ensure_same_request_hash(existing_payment, request_hash)
            return existing_payment

    @staticmethod
    def _build_payment_created_payload(payment: Payment) -> dict[str, Any]:
        return {"payment_id": str(payment.id)}

    @classmethod
    def _build_request_hash(cls, command: CreatePaymentCommand) -> str:
        payload = {
            "amount": cls._normalize_decimal(command.amount),
            "currency": command.currency.value,
            "description": command.description,
            "metadata": cls._normalize_json(command.metadata),
            "webhook_url": command.webhook_url,
        }
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized_payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _ensure_same_request_hash(payment: Payment, request_hash: str) -> None:
        if payment.request_hash == LEGACY_REQUEST_HASH:
            return
        if payment.request_hash != request_hash:
            raise IdempotencyConflictError(payment.idempotency_key)

    @classmethod
    def _normalize_json(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._normalize_json(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [cls._normalize_json(item) for item in value]
        if isinstance(value, Decimal):
            return cls._normalize_decimal(value)
        return value

    @staticmethod
    def _normalize_decimal(value: Decimal) -> str:
        return format(value.normalize(), "f")
