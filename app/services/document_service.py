from datetime import datetime, timezone

from app.schemas.document import DocumentCreate, DocumentResponse
from app.utils.id_generator import generate_entity_id

_DOCUMENT_STORE: dict[str, DocumentResponse] = {}


class DocumentService:
    def list_documents(self) -> list[DocumentResponse]:
        return sorted(_DOCUMENT_STORE.values(), key=lambda item: item.created_at, reverse=True)

    def create_document(self, payload: DocumentCreate) -> DocumentResponse:
        now = datetime.now(timezone.utc)
        document = DocumentResponse(
            id=generate_entity_id("doc"),
            status="uploaded",
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        _DOCUMENT_STORE[document.id] = document
        return document

    def get_document(self, document_id: str) -> DocumentResponse | None:
        return _DOCUMENT_STORE.get(document_id)
