from uuid import UUID


class PaymentNotFoundError(Exception):
    def __init__(self, payment_id: UUID) -> None:
        self.payment_id = payment_id
        super().__init__(f"Payment {payment_id} not found")


class RepositoryCalledOutsideTransactionError(Exception):
    pass


class WebhookDeliveryError(Exception):
    def __init__(self, url: str, attempts: int, last_error: Exception) -> None:
        self.url = url
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Webhook delivery to {url} failed after {attempts} attempts: {last_error}",
        )
