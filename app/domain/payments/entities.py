from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class Payment:
    id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    created_at: datetime
