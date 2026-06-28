from fastapi import APIRouter, HTTPException, status

from app.db import ping_database
from app.logger import get_logger
from app.schemas.health import HealthResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Run a backend health check",
    description=(
        "Verify the API process is alive and confirm the configured database can be reached "
        "with a lightweight connectivity probe."
    ),
)
async def health_check() -> HealthResponse:
    """
    Run the service health check.

    This endpoint performs a lightweight application liveness check and then
    verifies database connectivity using the shared async database layer.

    Returns:
        A simple health payload indicating API and database readiness.

    Raises:
        HTTPException: Returned when the database ping or response assembly fails.
    """
    try:
        await ping_database()
        logger.info("Health check completed successfully.")
        return HealthResponse(status="ok", service="pdf-chatbot-backend", database="ok")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception in health check endpoint.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service health check failed",
        ) from exc
