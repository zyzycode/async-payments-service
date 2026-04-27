from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.payment_repository import PaymentRepository
from app.domain.payments.entities import Payment


class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        raise NotImplementedError

    async def add(self, payment: Payment) -> None:
        raise NotImplementedError
