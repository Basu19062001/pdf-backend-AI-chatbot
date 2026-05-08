from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logger import get_logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_processing_log import DocumentProcessingLog
from app.models.user import User
from app.schemas.document import DocumentResponse, DocumentUploadResponse
from app.services.chunk_service import ChunkService
from app.services.document_storage_service import DocumentStorageService, StoredDocumentFile
from app.services.document_validation_service import DocumentValidationService
from app.services.pdf_service import PDFService

logger = get_logger(__name__)


class DocumentService:
    """Persist and process uploaded PDF documents."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.validation_service = DocumentValidationService()
        self.storage_service = DocumentStorageService()
        self.pdf_service = PDFService()
        self.chunk_service = ChunkService()

    async def list_documents(self, user_id: uuid.UUID) -> list[DocumentResponse]:
        try:
            statement: Select[tuple[Document]] = (
                select(Document)
                .where(Document.user_id == user_id)
                .order_by(Document.created_at.desc())
            )
            documents = list((await self.session.scalars(statement)).all())
            return [DocumentResponse.model_validate(document) for document in documents]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list documents for user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load documents at the moment",
            ) from exc

    async def get_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> DocumentResponse | None:
        try:
            statement: Select[tuple[Document]] = select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
            document = await self.session.scalar(statement)
            if document is None:
                return None
            return DocumentResponse.model_validate(document)
        except SQLAlchemyError as exc:
            logger.exception("Failed to load document '%s' for user '%s'.", document_id, user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load the requested document at the moment",
            ) from exc

    async def upload_document(
        self,
        user: User,
        upload_file: UploadFile,
        title: str | None = None,
    ) -> DocumentUploadResponse:
        logger.info(
            "Starting PDF upload for user '%s'. incoming_file='%s' requested_title='%s'",
            user.id,
            upload_file.filename,
            title,
        )
        validated_upload = await self.validation_service.validate_upload(upload_file)
        logger.info(
            "Upload validation completed for user '%s'. original_file='%s' size_bytes=%s content_type='%s'",
            user.id,
            validated_upload.original_file_name,
            validated_upload.file_size_bytes,
            validated_upload.content_type,
        )
        stored_file: StoredDocumentFile | None = None
        document: Document | None = None

        try:
            logger.info(
                "Persisting uploaded PDF to storage for user '%s'. original_file='%s'",
                user.id,
                validated_upload.original_file_name,
            )
            stored_file = await self.storage_service.store_pdf(
                original_file_name=validated_upload.original_file_name,
                content=validated_upload.content,
            )
            logger.info(
                "Stored uploaded PDF for user '%s'. stored_file='%s' relative_path='%s'",
                user.id,
                stored_file.stored_file_name,
                stored_file.relative_path,
            )
            logger.info(
                "Creating processing document row for user '%s'. title='%s'",
                user.id,
                title or Path(stored_file.original_file_name).stem,
            )
            document = await self._create_processing_document(
                user_id=user.id,
                title=title,
                stored_file=stored_file,
                file_size_bytes=validated_upload.file_size_bytes,
            )
            logger.info(
                "Created processing document '%s' for user '%s'. status='%s'",
                document.id,
                user.id,
                document.status,
            )

            extraction_started_at = datetime.now(timezone.utc)
            logger.info(
                "Starting PDF extraction for document '%s'. absolute_path='%s'",
                document.id,
                stored_file.absolute_path,
            )
            extraction_result = await self.pdf_service.extract_document(stored_file.absolute_path)
            validated_pages = self.validation_service.validate_extracted_pages(extraction_result.page_texts)
            logger.info(
                "PDF extraction completed for document '%s'. pages=%s summary='%s'",
                document.id,
                len(validated_pages),
                extraction_result.summary,
            )
            await self._create_processing_log(
                document_id=document.id,
                step_name="extraction",
                status_value="completed",
                message=(
                    f"Extracted text from {len(validated_pages)} PDF pages using "
                    f"{extraction_result.summary}."
                ),
                started_at=extraction_started_at,
                completed_at=datetime.now(timezone.utc),
            )

            chunking_started_at = datetime.now(timezone.utc)
            logger.info(
                "Starting chunk generation for document '%s'. page_count=%s'",
                document.id,
                len(validated_pages),
            )
            chunks = self.chunk_service.split_pages(validated_pages)
            if not chunks:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Unable to generate text chunks from the uploaded PDF",
                )
            logger.info(
                "Chunk generation completed for document '%s'. chunks=%s",
                document.id,
                len(chunks),
            )
            await self._create_processing_log(
                document_id=document.id,
                step_name="chunking",
                status_value="completed",
                message=f"Prepared {len(chunks)} chunks from extracted PDF text.",
                started_at=chunking_started_at,
                completed_at=datetime.now(timezone.utc),
            )

            persistence_started_at = datetime.now(timezone.utc)
            logger.info(
                "Persisting chunks for document '%s'. chunk_count=%s",
                document.id,
                len(chunks),
            )
            for chunk in chunks:
                self.session.add(
                    DocumentChunk(
                        document_id=document.id,
                        pinecone_vector_id=f"{document.id}:{chunk.chunk_index}",
                        chunk_index=chunk.chunk_index,
                        page_number_start=chunk.page_number_start,
                        page_number_end=chunk.page_number_end,
                        chunk_text=chunk.chunk_text,
                        token_count=chunk.token_count,
                        embedding_model=None,
                    )
                )

            document.total_pages = len(validated_pages)
            document.status = "processed"
            document.processed_at = datetime.now(timezone.utc)
            document.error_message = None
            logger.info(
                "Updating processed document metadata for document '%s'. total_pages=%s status='%s'",
                document.id,
                document.total_pages,
                document.status,
            )
            await self._create_processing_log(
                document_id=document.id,
                step_name="persistence",
                status_value="completed",
                message=f"Saved {len(chunks)} chunks for processed PDF.",
                started_at=persistence_started_at,
                completed_at=datetime.now(timezone.utc),
            )
            logger.info("Committing processed upload transaction for document '%s'.", document.id)
            await self.session.commit()
            await self.session.refresh(document)
            logger.info("Uploaded and processed document '%s' for user '%s'.", document.id, user.id)
            return DocumentUploadResponse(
                document_id=document.id,
                status=document.status,
                pages=document.total_pages or 0,
                chunks=len(chunks),
            )
        except HTTPException as exc:
            logger.warning(
                "Upload pipeline returned an HTTP error for user '%s'. document_id='%s' detail='%s'",
                user.id,
                document.id if document is not None else None,
                exc.detail,
            )
            await self.session.rollback()
            if document is not None:
                await self._mark_document_failed(document.id, str(exc.detail))
            elif stored_file is not None:
                logger.info(
                    "Deleting stored file after upload failure for user '%s'. path='%s'",
                    user.id,
                    stored_file.absolute_path,
                )
                await self.storage_service.delete_file(stored_file.absolute_path)
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Database error while uploading a PDF for user '%s'.", user.id)
            if document is not None:
                await self._mark_document_failed(document.id, "Failed to persist uploaded PDF metadata")
            elif stored_file is not None:
                logger.info(
                    "Deleting stored file after database failure for user '%s'. path='%s'",
                    user.id,
                    stored_file.absolute_path,
                )
                await self.storage_service.delete_file(stored_file.absolute_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to upload the PDF at the moment",
            ) from exc
        except Exception as exc:
            await self.session.rollback()
            logger.exception("Unexpected error while uploading a PDF for user '%s'.", user.id)
            if document is not None:
                await self._mark_document_failed(document.id, "Unexpected error while processing uploaded PDF")
            elif stored_file is not None:
                logger.info(
                    "Deleting stored file after unexpected upload failure for user '%s'. path='%s'",
                    user.id,
                    stored_file.absolute_path,
                )
                await self.storage_service.delete_file(stored_file.absolute_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to upload the PDF at the moment",
            ) from exc

    async def _create_processing_document(
        self,
        user_id: uuid.UUID,
        title: str | None,
        stored_file: StoredDocumentFile,
        file_size_bytes: int,
    ) -> Document:
        logger.info(
            "Creating document metadata row for user '%s'. original_file='%s' stored_file='%s'",
            user_id,
            stored_file.original_file_name,
            stored_file.stored_file_name,
        )
        document = Document(
            user_id=user_id,
            title=title or Path(stored_file.original_file_name).stem,
            original_file_name=stored_file.original_file_name,
            stored_file_name=stored_file.stored_file_name,
            file_path=stored_file.relative_path,
            file_url=None,
            file_type="pdf",
            file_size_bytes=file_size_bytes,
            status="processing",
            uploaded_at=datetime.now(timezone.utc),
            error_message=None,
        )
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        logger.info(
            "Document metadata committed for document '%s'. file_path='%s' status='%s'",
            document.id,
            document.file_path,
            document.status,
        )
        await self._create_processing_log(
            document_id=document.id,
            step_name="validation",
            status_value="completed",
            message="Validated uploaded PDF metadata and file content.",
            started_at=document.uploaded_at,
            completed_at=document.uploaded_at,
        )
        await self._create_processing_log(
            document_id=document.id,
            step_name="storage",
            status_value="completed",
            message=f"Stored uploaded PDF at '{stored_file.relative_path}'.",
            started_at=document.uploaded_at,
            completed_at=datetime.now(timezone.utc),
        )
        logger.info("Committed initial processing logs for document '%s'.", document.id)
        await self.session.commit()
        return document

    async def _create_processing_log(
        self,
        document_id: uuid.UUID,
        step_name: str,
        status_value: str,
        message: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        self.session.add(
            DocumentProcessingLog(
                document_id=document_id,
                step_name=step_name,
                status=status_value,
                message=message,
                started_at=started_at,
                completed_at=completed_at,
            )
        )

    async def _mark_document_failed(self, document_id: uuid.UUID, message: str) -> None:
        try:
            logger.warning("Marking document '%s' as failed. reason='%s'", document_id, message)
            document = await self.session.get(Document, document_id)
            if document is None:
                return
            document.status = "failed"
            document.error_message = message
            document.processed_at = None
            await self._create_processing_log(
                document_id=document_id,
                step_name="processing",
                status_value="failed",
                message=message,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            await self.session.commit()
            logger.warning("Marked document '%s' as failed. reason='%s'", document_id, message)
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Failed to persist failed status for document '%s'.", document_id)
