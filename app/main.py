import secrets

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.backend.api.router import api_router
from app.core.config import settings

security = HTTPBasic()


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


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        debug=settings.DEBUG,
    )
    app.include_router(api_router, prefix=settings.API_V1_STR)

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
