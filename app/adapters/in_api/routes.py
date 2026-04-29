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
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Отсутствует или неверен X-API-Key.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Не передан Idempotency-Key или тело запроса не прошло валидацию.",
        },
    },
)
async def create_payment(
    request: CreatePaymentRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    use_case: Annotated[CreatePaymentUseCase, Depends(get_create_payment_use_case)],
) -> CreatePaymentResponse:
    """Создает платеж и ставит его в асинхронную обработку.

    Эндпоинт является внешним контрактом для создания платежа. При успешном
    запросе платеж сохраняется со статусом `pending`, а событие `payments.new`
    создается через outbox для последующей публикации в RabbitMQ.

    Идемпотентность:
        Заголовок `Idempotency-Key` обязателен. Если платеж с таким ключом уже
        существует, новый платеж и outbox event не создаются, а клиент получает
        данные ранее созданного платежа.

    Возможные статусы платежа:
        `pending` сразу после создания, затем `succeeded` или `failed` после
        обработки consumer-ом.

    Ошибки:
        401: отсутствует или неверен `X-API-Key`.
        422: не передан `Idempotency-Key` или тело запроса не прошло валидацию.

    Returns:
        Ответ `202 Accepted` с `payment_id`, текущим статусом и датой создания.
    """
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
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Отсутствует или неверен X-API-Key.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Платеж с указанным payment_id не найден.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "payment_id не является валидным UUID.",
        },
    },
)
async def get_payment(
    payment_id: UUID,
    use_case: Annotated[GetPaymentUseCase, Depends(get_get_payment_use_case)],
) -> PaymentResponse:
    """Возвращает детальную информацию о платеже.

    Эндпоинт является внешним контрактом для чтения состояния платежа. Он
    возвращает сумму, валюту, описание, metadata, webhook URL, idempotency key,
    текущий статус и даты создания/обработки.

    Возможные статусы платежа:
        `pending`, `succeeded`, `failed`.

    Ошибки:
        401: отсутствует или неверен `X-API-Key`.
        404: платеж с указанным `payment_id` не найден.
        422: `payment_id` не является валидным UUID.

    Returns:
        Детальное представление платежа.
    """
    try:
        payment = await use_case.execute(payment_id)
    except PaymentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return PaymentResponse.from_domain(payment)


router.include_router(payments_router)
