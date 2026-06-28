import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.api.auth_dependencies import CurrentAuthContext
from app.db import get_db_session
from app.logger import get_logger
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentUploadResponse
from app.services.document_service import DocumentService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentListResponse:
    """
    List all uploaded documents for the current authenticated user.

    This endpoint returns the caller's document metadata ordered from newest
    to oldest. Only documents owned by the authenticated user are included.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        A list of document records belonging to the authenticated user.

    Raises:
        HTTPException: Returned when the user's documents cannot be loaded.
    """
    try:
        service = DocumentService(session)
        response = DocumentListResponse(items=await service.list_documents(auth_context.user.id))
        logger.info("Listed documents for authenticated user '%s'.", auth_context.user.id)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception while listing documents for user '%s'.", auth_context.user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load documents at the moment",
        ) from exc


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
) -> DocumentUploadResponse:
    """
    Upload, process, and persist a PDF document for the authenticated user.

    This endpoint accepts a multipart PDF upload, validates the incoming file,
    writes it to temporary local storage for extraction, creates the backing
    document row, extracts page text, generates chunks, persists those chunks
    to PostgreSQL, and records processing logs for each major step. The
    temporary PDF file is removed after processing finishes or fails.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.
        file: Uploaded PDF file received as multipart/form-data.
        title: Optional document title override supplied by the client.

    Returns:
        A concise processing result containing the document ID, final status,
        extracted page count, and persisted chunk count.

    Raises:
        HTTPException: Returned when validation, storage, extraction, chunking,
            or persistence fails.
    """
    try:
        service = DocumentService(session)
        normalized_title = title.strip() if title and title.strip() else None
        response = await service.upload_document(auth_context.user, file, normalized_title)
        logger.info("Document upload completed for user '%s'. document_id='%s'", auth_context.user.id, response.document_id)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception while uploading a document for user '%s'.", auth_context.user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to upload the PDF at the moment",
        ) from exc


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentResponse:
    """
    Load a single uploaded document owned by the authenticated user.

    This endpoint resolves one document by ID while enforcing document
    ownership through the authenticated user context.

    Args:
        document_id: Unique identifier of the document to load.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        The persisted document metadata for the requested document.

    Raises:
        HTTPException: Returned when the document does not exist or cannot be loaded.
    """
    try:
        service = DocumentService(session)
        document = await service.get_document(auth_context.user.id, document_id)
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        logger.info("Loaded document '%s' for authenticated user '%s'.", document_id, auth_context.user.id)
        return document
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled exception while loading document '%s' for user '%s'.",
            document_id,
            auth_context.user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load the requested document at the moment",
        ) from exc
