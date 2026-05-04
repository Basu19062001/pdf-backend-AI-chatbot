from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.schemas.chat import ChatMessageCreate, ChatSessionCreate


class ChatService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_sessions(self) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .order_by(ChatSession.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def create_session(self, payload: ChatSessionCreate) -> ChatSession:
        session = ChatSession(**payload.model_dump())
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        return self.db.scalars(stmt).first()

    def add_message(self, session_id: str, payload: ChatMessageCreate) -> ChatSession | None:
        session = self.db.get(ChatSession, session_id)
        if not session:
            return None

        message = ChatMessage(session_id=session_id, **payload.model_dump())
        self.db.add(message)
        self.db.commit()
        return self.get_session(session_id)
