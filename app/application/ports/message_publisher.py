from typing import Any, Protocol


class MessagePublisher(Protocol):
    async def publish(
        self,
        exchange: str,
        routing_key: str,
        message: dict[str, Any],
    ) -> None:
        raise NotImplementedError
