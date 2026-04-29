from dataclasses import dataclass
from uuid import UUID

from app.application.errors import PaymentNotFoundError
from app.application.ports.payment_repository import PaymentRepository
from app.application.ports.transaction_manager import TransactionManager
from app.domain.payments.entities import Payment


@dataclass(slots=True)
class GetPaymentUseCase:
    payment_repository: PaymentRepository
    transaction_manager: TransactionManager

    async def execute(self, payment_id: UUID) -> Payment:
        async with self.transaction_manager:
            payment = await self.payment_repository.get_by_id(payment_id)
            if payment is None:
                raise PaymentNotFoundError(payment_id)
            return payment
