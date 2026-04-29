from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.adapters.in_api.dependencies import (
    get_create_payment_use_case,
    get_get_payment_use_case,
    verify_api_key,
)
from app.adapters.in_api.schemas import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentResponse,
)
from app.application.errors import PaymentNotFoundError
from app.application.use_cases import (
    CreatePaymentCommand,
    CreatePaymentUseCase,
    GetPaymentUseCase,
)

router = APIRouter()
payments_router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/health", tags=["system"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@payments_router.post(
    "",
    response_model=CreatePaymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_payment(
    request: CreatePaymentRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    use_case: Annotated[CreatePaymentUseCase, Depends(get_create_payment_use_case)],
) -> CreatePaymentResponse:
    payment = await use_case.execute(
        CreatePaymentCommand(
            amount=request.amount,
            currency=request.currency,
            description=request.description,
            metadata=request.metadata,
            webhook_url=str(request.webhook_url),
            idempotency_key=idempotency_key,
        ),
    )
    return CreatePaymentResponse.from_domain(payment)


@payments_router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
)
async def get_payment(
    payment_id: UUID,
    use_case: Annotated[GetPaymentUseCase, Depends(get_get_payment_use_case)],
) -> PaymentResponse:
    try:
        payment = await use_case.execute(payment_id)
    except PaymentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return PaymentResponse.from_domain(payment)


router.include_router(payments_router)
