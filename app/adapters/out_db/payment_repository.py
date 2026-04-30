from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.out_db.models import PaymentModel
from app.adapters.out_db.transaction_boundary import ensure_application_transaction
from app.application.errors import DuplicateIdempotencyKeyError
from app.application.ports.payment_repository import PaymentRepository
from app.application.ports.types import PaymentCreateData
from app.domain.payments.entities import Currency, Payment, PaymentStatus


def payment_to_domain(model: PaymentModel) -> Payment:
    return Payment(
        id=model.id,
        amount=model.amount,
        currency=Currency(model.currency),
        description=model.description,
        metadata=model.metadata_,
        status=PaymentStatus(model.status),
        idempotency_key=model.idempotency_key,
        request_hash=model.request_hash,
        webhook_url=model.webhook_url,
        created_at=model.created_at,
        processed_at=model.processed_at,
    )


class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: PaymentCreateData) -> Payment:
        ensure_application_transaction(self._session)
        model = PaymentModel(
            id=uuid4(),
            amount=data.amount,
            currency=data.currency.value,
            description=data.description,
            metadata_=data.metadata,
            status=PaymentStatus.PENDING.value,
            idempotency_key=data.idempotency_key,
            request_hash=data.request_hash,
            webhook_url=data.webhook_url,
            created_at=datetime.now(timezone.utc),
            processed_at=None,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if self._is_idempotency_key_violation(exc):
                raise DuplicateIdempotencyKeyError(data.idempotency_key) from exc
            raise
        return payment_to_domain(model)

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        ensure_application_transaction(self._session)
        model = await self._session.get(PaymentModel, payment_id)
        if model is None:
            return None
        return payment_to_domain(model)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        ensure_application_transaction(self._session)
        result = await self._session.execute(
            select(PaymentModel).where(PaymentModel.idempotency_key == idempotency_key),
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return payment_to_domain(model)

    async def update_status(
        self,
        payment_id: UUID,
        status: PaymentStatus,
        processed_at: datetime | None = None,
    ) -> Payment:
        ensure_application_transaction(self._session)
        model = await self._session.get(PaymentModel, payment_id)
        if model is None:
            raise ValueError(f"Payment {payment_id} not found")

        model.status = status.value
        model.processed_at = processed_at or datetime.now(timezone.utc)
        await self._session.flush()
        return payment_to_domain(model)

    @staticmethod
    def _is_idempotency_key_violation(exc: IntegrityError) -> bool:
        error_text = str(exc.orig)
        return (
            "ix_payments_idempotency_key" in error_text
            or "payments_idempotency_key" in error_text
            or "idempotency_key" in error_text
        )
