from fastapi import APIRouter

from app.backend.api.routes.chat import router as chat_router
from app.backend.api.routes.documents import router as document_router
from app.backend.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(document_router, prefix="/documents", tags=["documents"])
api_router.include_router(chat_router, prefix="/chats", tags=["chats"])
