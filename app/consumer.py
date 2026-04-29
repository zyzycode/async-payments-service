from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.adapters.in_consumer.handlers import register_handlers
from app.adapters.in_consumer.topology import payment_dlq, payment_dlx
from app.core.logging import configure_logging
from app.core.settings import settings

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

register_handlers(broker)


@app.after_startup
async def declare_dead_letter_topology() -> None:
    configure_logging()
    dlx = await broker.declare_exchange(payment_dlx())
    dlq = await broker.declare_queue(payment_dlq())
    await dlq.bind(dlx, routing_key=settings.payment_dlq)
