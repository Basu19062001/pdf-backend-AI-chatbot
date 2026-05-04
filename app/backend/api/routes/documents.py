from fastapi import APIRouter, HTTPException, status
from app.schemas.document import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
)
from app.services.document_service import DocumentService

router = APIRouter()


@router.get("/", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    service = DocumentService()
    return DocumentListResponse(items=service.list_documents())


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: DocumentCreate,
) -> DocumentResponse:
    service = DocumentService()
    return service.create_document(payload)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str) -> DocumentResponse:
    service = DocumentService()
    document = service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document
