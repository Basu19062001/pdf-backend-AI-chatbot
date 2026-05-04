from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.schemas.document import DocumentCreate


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_documents(self) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def create_document(self, payload: DocumentCreate) -> Document:
        document = Document(**payload.model_dump())
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_document(self, document_id: str) -> Document | None:
        return self.db.get(Document, document_id)
