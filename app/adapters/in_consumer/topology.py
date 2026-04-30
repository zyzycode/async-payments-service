from dataclasses import dataclass

from faststream.rabbit import RabbitExchange, RabbitQueue

from app.core.settings import settings

PAYMENT_NEW_TOTAL_PROCESSING_ATTEMPTS = 3
PAYMENT_PROCESSING_RETRY_DELAYS_SECONDS = (1, 2)


@dataclass(frozen=True, slots=True)
class PaymentRetryQueueConfig:
    name: str
    routing_key: str
    delay_seconds: int


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

    Очередь является quorum queue и получает события `payments.new`. Retry
    обработки реализован явно через retry-очереди с TTL: при ошибке consumer
    публикует сообщение в очередь задержки, а RabbitMQ после TTL возвращает его
    обратно в `payments.new`.

    `x-delivery-limit` оставлен как дополнительная защита для неожиданных
    nack/redelivery вне ручной retry policy. RabbitMQ quorum queue считает
    redelivery, а не первую доставку, поэтому для 3 total processing attempts
    используется значение `2`.
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


def payment_retry_queue_configs() -> tuple[PaymentRetryQueueConfig, ...]:
    """Возвращает retry policy обработки платежей.

    Для 3 total attempts нужны две задержки между попытками: 1 секунда перед
    второй обработкой и 2 секунды перед третьей. Сообщение публикуется в retry
    queue с соответствующим routing key, затем RabbitMQ по TTL dead-letter-ит
    его обратно в exchange `payments` с routing key `payments.new`.
    """
    return tuple(
        PaymentRetryQueueConfig(
            name=f"{settings.payment_new_queue}.retry.{delay_seconds}s",
            routing_key=f"{settings.payment_new_routing_key}.retry.{delay_seconds}s",
            delay_seconds=delay_seconds,
        )
        for delay_seconds in PAYMENT_PROCESSING_RETRY_DELAYS_SECONDS
    )


def payment_retry_queues() -> tuple[RabbitQueue, ...]:
    """Возвращает очереди задержки для exponential backoff обработки платежей."""
    return tuple(
        RabbitQueue(
            config.name,
            durable=True,
            routing_key=config.routing_key,
            arguments={
                "x-message-ttl": config.delay_seconds * 1000,
                "x-dead-letter-exchange": settings.payment_exchange,
                "x-dead-letter-routing-key": settings.payment_new_routing_key,
            },
        )
        for config in payment_retry_queue_configs()
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
