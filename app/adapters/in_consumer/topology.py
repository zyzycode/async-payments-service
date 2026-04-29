from faststream.rabbit import RabbitExchange, RabbitQueue

from app.core.settings import settings

PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS = 3


def payment_exchange() -> RabbitExchange:
    return RabbitExchange(
        settings.payment_exchange,
        durable=True,
    )


def payment_dlx() -> RabbitExchange:
    return RabbitExchange(
        settings.payment_dlx,
        durable=True,
    )


def payment_new_queue() -> RabbitQueue:
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
    return RabbitQueue(
        settings.payment_dlq,
        durable=True,
        routing_key=settings.payment_dlq,
        arguments={
            "x-queue-type": "quorum",
        },
    )
