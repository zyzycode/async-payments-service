from faststream.rabbit import RabbitExchange, RabbitQueue

from app.core.settings import settings

PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS = 3


def payment_exchange() -> RabbitExchange:
    """Возвращает exchange, через который публикуются события новых платежей."""
    return RabbitExchange(
        settings.payment_exchange,
        durable=True,
    )


def payment_dlx() -> RabbitExchange:
    """Возвращает dead-letter exchange для окончательно упавших сообщений."""
    return RabbitExchange(
        settings.payment_dlx,
        durable=True,
    )


def payment_new_queue() -> RabbitQueue:
    """Возвращает основную очередь обработки новых платежей.

    Очередь является quorum queue и получает события `payments.new`. Для DLQ
    гарантии она настроена так, чтобы сообщение после 3 неуспешных обработок
    попадало в `payment_dlx` с routing key `PAYMENT_DLQ`.

    RabbitMQ quorum queue считает redelivery, а не первую доставку. Поэтому для
    3 total processing attempts используется `x-delivery-limit = 2`: первичная
    доставка плюс 2 повторные доставки.
    """
    return RabbitQueue(
        settings.payment_new_queue,
        durable=True,
        routing_key=settings.payment_new_routing_key,
        arguments={
            "x-queue-type": "quorum",
            # RabbitMQ counts redeliveries here, so 3 total processing attempts
            # means initial delivery plus 2 redeliveries.
            "x-delivery-limit": PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS - 1,
            "x-dead-letter-exchange": settings.payment_dlx,
            "x-dead-letter-routing-key": settings.payment_dlq,
        },
    )


def payment_dlq() -> RabbitQueue:
    """Возвращает очередь для сообщений, не обработанных после лимита попыток."""
    return RabbitQueue(
        settings.payment_dlq,
        durable=True,
        routing_key=settings.payment_dlq,
        arguments={
            "x-queue-type": "quorum",
        },
    )
