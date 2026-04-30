from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.adapters.in_consumer.handlers import register_handlers
from app.adapters.in_consumer.topology import (
    payment_dlq,
    payment_dlx,
    payment_exchange,
    payment_retry_queues,
)
from app.core.logging import configure_logging
from app.core.settings import settings

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

register_handlers(broker)


@app.after_startup
async def declare_payment_topology() -> None:
    configure_logging()
    exchange = await broker.declare_exchange(payment_exchange())
    dlx = await broker.declare_exchange(payment_dlx())
    dlq = await broker.declare_queue(payment_dlq())
    await dlq.bind(dlx, routing_key=settings.payment_dlq)
    for retry_queue_config in payment_retry_queues():
        retry_queue = await broker.declare_queue(retry_queue_config)
        await retry_queue.bind(exchange, routing_key=retry_queue_config.routing_key)
