from fastapi import FastAPI

from app.adapters.in_api.routes import router as api_router
from app.core.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
    )
    app.include_router(api_router)
    return app


app = create_app()
