from uuid import UUID

from pydantic import BaseModel


class PaymentNewMessage(BaseModel):
    payment_id: UUID
