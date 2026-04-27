from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.adapters.in_consumer.handlers import register_handlers
from app.core.config import settings

broker = RabbitBroker(settings.rabbit_url)
app = FastStream(broker)

register_handlers(broker)
