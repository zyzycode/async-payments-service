from collections.abc import AsyncIterator
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.out_db.database import get_session
from app.adapters.out_db.outbox_repository import SqlAlchemyOutboxRepository
from app.adapters.out_db.payment_repository import SqlAlchemyPaymentRepository
from app.adapters.out_db.transaction_manager import SqlAlchemyTransactionManager
from app.application.use_cases import CreatePaymentUseCase, GetPaymentUseCase
from app.core.settings import settings


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    expected_api_key = settings.api_key.get_secret_value()
    if x_api_key is None or not compare_digest(x_api_key, expected_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


async def get_create_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[CreatePaymentUseCase]:
    yield CreatePaymentUseCase(
        payment_repository=SqlAlchemyPaymentRepository(session),
        outbox_repository=SqlAlchemyOutboxRepository(session),
        transaction_manager=SqlAlchemyTransactionManager(session),
        payment_exchange=settings.payment_exchange,
        payment_new_routing_key=settings.payment_new_routing_key,
    )


async def get_get_payment_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[GetPaymentUseCase]:
    yield GetPaymentUseCase(
        payment_repository=SqlAlchemyPaymentRepository(session),
        transaction_manager=SqlAlchemyTransactionManager(session),
    )
