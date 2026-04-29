from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.out_db.transaction_boundary import APPLICATION_TRANSACTION_ACTIVE
from app.application.ports.transaction_manager import TransactionManager


class SqlAlchemyTransactionManager(TransactionManager):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> "SqlAlchemyTransactionManager":
        if self._session.info.get(APPLICATION_TRANSACTION_ACTIVE):
            raise RuntimeError("Application transaction boundary is already active")
        if self._session.in_transaction():
            raise RuntimeError("SQLAlchemy session already has an active transaction")

        await self._session.begin()
        self._session.info[APPLICATION_TRANSACTION_ACTIVE] = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self.commit()
                return
            await self.rollback()
        finally:
            self._session.info.pop(APPLICATION_TRANSACTION_ACTIVE, None)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
