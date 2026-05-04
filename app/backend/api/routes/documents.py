from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.backend.api.dependencies import get_db
from app.schemas.document import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
)
from app.services.document_service import DocumentService

router = APIRouter()


@router.get("/", response_model=DocumentListResponse)
def list_documents(db: Session = Depends(get_db)) -> DocumentListResponse:
    service = DocumentService(db)
    return DocumentListResponse(items=service.list_documents())


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    service = DocumentService(db)
    return service.create_document(payload)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentResponse:
    service = DocumentService(db)
    document = service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document
