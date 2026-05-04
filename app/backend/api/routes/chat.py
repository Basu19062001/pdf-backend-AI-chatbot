from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.backend.api.dependencies import get_db
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()


@router.get("/sessions", response_model=ChatSessionListResponse)
def list_sessions(db: Session = Depends(get_db)) -> ChatSessionListResponse:
    service = ChatService(db)
    return ChatSessionListResponse(items=service.list_sessions())


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: ChatSessionCreate,
    db: Session = Depends(get_db),
) -> ChatSessionResponse:
    service = ChatService(db)
    return service.create_session(payload)


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)) -> ChatSessionResponse:
    service = ChatService(db)
    session = service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    session_id: str,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
) -> ChatSessionResponse:
    service = ChatService(db)
    session = service.add_message(session_id=session_id, payload=payload)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session
