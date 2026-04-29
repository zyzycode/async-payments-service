from sqlalchemy.ext.asyncio import AsyncSession

from app.application.errors import RepositoryCalledOutsideTransactionError

APPLICATION_TRANSACTION_ACTIVE = "application_transaction_active"


def ensure_application_transaction(session: AsyncSession) -> None:
    if not session.info.get(APPLICATION_TRANSACTION_ACTIVE):
        raise RepositoryCalledOutsideTransactionError(
            "Repository method was called outside application transaction boundary",
        )
