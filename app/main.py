from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.backend.api.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F403,F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_application()
