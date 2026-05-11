from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from app.utils import utc_now
from app.utils.id_generator import generate_entity_id

_SESSION_STORE: dict[str, ChatSessionResponse] = {}


class ChatService:
    def list_sessions(self) -> list[ChatSessionResponse]:
        return sorted(_SESSION_STORE.values(), key=lambda item: item.created_at, reverse=True)

    def create_session(self, payload: ChatSessionCreate) -> ChatSessionResponse:
        now = utc_now()
        session = ChatSessionResponse(
            id=generate_entity_id("ses"),
            status="active",
            created_at=now,
            updated_at=now,
            messages=[],
            **payload.model_dump(),
        )
        _SESSION_STORE[session.id] = session
        return session

    def get_session(self, session_id: str) -> ChatSessionResponse | None:
        return _SESSION_STORE.get(session_id)

    def add_message(self, session_id: str, payload: ChatMessageCreate) -> ChatSessionResponse | None:
        session = _SESSION_STORE.get(session_id)
        if not session:
            return None

        now = utc_now()
        message = ChatMessageResponse(
            id=generate_entity_id("msg"),
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        updated_session = session.model_copy(
            update={
                "messages": [*session.messages, message],
                "updated_at": now,
            }
        )
        _SESSION_STORE[session_id] = updated_session
        return updated_session
