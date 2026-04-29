from typing import Any

from faststream.rabbit import RabbitBroker

from app.application.ports.message_publisher import MessagePublisher


class RabbitMessagePublisher(MessagePublisher):
    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish(
        self,
        exchange: str,
        routing_key: str,
        message: dict[str, Any],
    ) -> None:
        await self._broker.publish(
            message,
            exchange=exchange,
            routing_key=routing_key,
            persist=True,
        )
