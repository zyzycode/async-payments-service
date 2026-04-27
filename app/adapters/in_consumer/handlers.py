from faststream.rabbit import RabbitBroker


def register_handlers(broker: RabbitBroker) -> None:
    _ = broker
    # Register @broker.subscriber handlers here when payment use cases are added.
