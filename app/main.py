from contextlib import asynccontextmanager
import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.backend.api.router import api_router
from app.cache import close_redis, initialize_redis
from app.core.config import settings
from app.db import close_database, get_session_factory, initialize_database
from app.logger import get_logger, setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.auth_session_service import AuthSessionService

security = HTTPBasic()
setup_logging()
logger = get_logger(__name__)


def verify_docs_access(
    credentials: HTTPBasicCredentials = Depends(security),
) -> HTTPBasicCredentials:
    username_ok = secrets.compare_digest(credentials.username, settings.DOC_ROOT_USERNAME)
    password_ok = secrets.compare_digest(credentials.password, settings.DOC_ROOT_PASSWORD)

    if username_ok and password_ok:
        return credentials

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid documentation credentials",
        headers={"WWW-Authenticate": "Basic"},
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Initializing application resources.")
    await initialize_database()
    await initialize_redis()
    session_factory = get_session_factory()
    async with session_factory() as session:
        await AuthSessionService(session).purge_expired_sessions()
    try:
        yield
    finally:
        await close_redis()
        await close_database()
        logger.info("Application resources shut down cleanly.")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix=settings.API_V1_STR)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health", include_in_schema=False)
    def root_healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": settings.PROJECT_NAME}

    if settings.DOCS_ENABLED:

        @app.get(settings.OPENAPI_URL, include_in_schema=False)
        def protected_openapi(_: HTTPBasicCredentials = Depends(verify_docs_access)) -> JSONResponse:
            return JSONResponse(
                get_openapi(
                    title=app.title,
                    description=app.description,
                    version=app.version,
                    routes=app.routes,
                )
            )

        @app.get(settings.DOCS_URL, include_in_schema=False)
        def protected_swagger(_: HTTPBasicCredentials = Depends(verify_docs_access)) -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url=settings.OPENAPI_URL,
                title=f"{app.title} - Swagger UI",
            )

        @app.get(settings.REDOC_URL, include_in_schema=False)
        def protected_redoc(_: HTTPBasicCredentials = Depends(verify_docs_access)) -> HTMLResponse:
            return get_redoc_html(
                openapi_url=settings.OPENAPI_URL,
                title=f"{app.title} - ReDoc",
            )

    return app


app = create_application()
