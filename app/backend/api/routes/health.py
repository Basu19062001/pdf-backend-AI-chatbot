from fastapi import APIRouter

from app.db import ping_database
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    await ping_database()
    return HealthResponse(status="ok", service="pdf-chatbot-backend", database="ok")
