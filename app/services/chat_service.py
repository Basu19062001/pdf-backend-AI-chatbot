from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import Select, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.logger import get_logger
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.message_source import MessageSource
from app.models.usage_log import UsageLog
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
    ChatSourceResponse,
    ChatTurnResponse,
)
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import GeneratedAnswer, LLMService
from app.services.pinecone_service import PineconeService, VectorMatch
from app.utils import utc_now

logger = get_logger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float
    source_rank: int


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = EmbeddingService()
        self.pinecone_service = PineconeService()
        self.llm_service = LLMService()

    async def list_sessions(self, user_id: uuid.UUID) -> list[ChatSessionSummaryResponse]:
        try:
            statement: Select[tuple[ChatSession]] = (
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.updated_at.desc())
            )
            sessions = list((await self.session.scalars(statement)).all())
            return [self._to_session_summary_response(session) for session in sessions]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list chat sessions for user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load chat sessions at the moment",
            ) from exc

    async def create_session(self, user_id: uuid.UUID, payload: ChatSessionCreate) -> ChatSessionResponse:
        document = await self._get_owned_document(user_id, payload.document_id)
        now = utc_now()
        session = ChatSession(
            id=uuid.uuid4(),
            user_id=user_id,
            document_id=document.id,
            title=payload.title.strip() if payload.title and payload.title.strip() else document.title,
            status="active",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            self.session.add(session)
            await self.session.commit()
            await self.session.refresh(session)
            return await self.get_session(user_id, session.id)
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Failed to create chat session for user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create a chat session at the moment",
            ) from exc

    async def get_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSessionResponse | None:
        session = await self._load_session(user_id, session_id)
        if session is None:
            return None
        return self._to_session_response(session)

    async def answer_question(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        payload: ChatMessageCreate,
    ) -> ChatTurnResponse:
        session = await self._require_session(user_id, session_id)
        document = await self._get_owned_document(user_id, session.document_id)
        self._ensure_document_ready(document)

        user_message = await self._create_user_message(session, payload.content)
        retrieved_chunks = await self._retrieve_context(
            user_id=user_id,
            document=document,
            question=payload.content,
        )
        generated_answer = await self.llm_service.answer_question(
            prompt=self._build_prompt(
                session=session,
                document=document,
                question=payload.content,
                retrieved_chunks=retrieved_chunks,
            ),
            user_reference=str(user_id),
            model_name=payload.model_name,
        )
        assistant_message = await self._create_assistant_message(
            session=session,
            generated_answer=generated_answer,
            retrieved_chunks=retrieved_chunks,
        )
        full_session = await self._require_session(user_id, session_id)
        return ChatTurnResponse(
            session=self._to_session_response(full_session),
            user_message=self._to_message_response(user_message),
            assistant_message=self._to_message_response(assistant_message),
        )

    async def stream_answer(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        payload: ChatMessageCreate,
    ) -> AsyncIterator[str]:
        session = await self._require_session(user_id, session_id)
        document = await self._get_owned_document(user_id, session.document_id)
        self._ensure_document_ready(document)

        user_message = await self._create_user_message(session, payload.content)
        retrieved_chunks = await self._retrieve_context(
            user_id=user_id,
            document=document,
            question=payload.content,
        )

        assistant_message_id = uuid.uuid4()
        model_name = (payload.model_name or settings.CHAT_MODEL).strip()
        prompt = self._build_prompt(
            session=session,
            document=document,
            question=payload.content,
            retrieved_chunks=retrieved_chunks,
        )

        yield self._sse_event(
            "message_start",
            {
                "session_id": str(session.id),
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant_message_id),
                "model_name": model_name,
                "sources": [self._source_payload(item) for item in retrieved_chunks],
            },
        )

        try:
            async with self.llm_service.stream_answer(
                prompt=prompt,
                user_reference=str(user_id),
                model_name=model_name,
            ) as stream:
                async for event in stream:
                    if event.type == "response.output_text.delta" and event.delta:
                        yield self._sse_event("message_delta", {"delta": event.delta})
                    elif event.type == "response.failed":
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="OpenAI chat request failed",
                        )

                final_response = await stream.get_final_response()

            generated_answer = self.llm_service.finalize_streamed_answer(
                final_response,
                fallback_model_name=model_name,
            )
            assistant_message = await self._create_assistant_message(
                session=session,
                generated_answer=generated_answer,
                retrieved_chunks=retrieved_chunks,
                message_id=assistant_message_id,
            )
            yield self._sse_event(
                "message_complete",
                {
                    "assistant_message": self._message_payload(assistant_message),
                },
            )
        except asyncio.CancelledError:
            logger.info("Streaming client disconnected for chat session '%s'.", session.id)
            raise
        except HTTPException as exc:
            logger.warning("Streaming chat failed for session '%s': %s", session.id, exc.detail)
            yield self._sse_event("error", {"detail": exc.detail})
        except Exception:
            logger.exception("Unexpected streaming error for chat session '%s'.", session.id)
            yield self._sse_event("error", {"detail": "Unable to stream the assistant response"})

    async def _get_owned_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        statement: Select[tuple[Document]] = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        document = await self.session.scalar(statement)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return document

    def _ensure_document_ready(self, document: Document) -> None:
        if document.status != "processed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The selected document is not ready for chat yet",
            )

    async def _load_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession | None:
        statement: Select[tuple[ChatSession]] = (
            select(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .options(
                selectinload(ChatSession.messages).selectinload(ChatMessage.sources),
            )
        )
        return await self.session.scalar(statement)

    async def _require_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession:
        session = await self._load_session(user_id, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    async def _create_user_message(self, session: ChatSession, content: str) -> ChatMessage:
        now = utc_now()
        message = ChatMessage(
            id=uuid.uuid4(),
            chat_session_id=session.id,
            role="user",
            content=content.strip(),
            created_at=now,
        )
        session.last_message_at = now
        session.updated_at = now
        try:
            self.session.add(message)
            await self.session.commit()
            await self.session.refresh(message)
            return message
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Failed to persist user message for chat session '%s'.", session.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to save the chat message",
            ) from exc

    async def _retrieve_context(
        self,
        *,
        user_id: uuid.UUID,
        document: Document,
        question: str,
    ) -> list[RetrievedChunk]:
        query_embedding = (await self.embedding_service.create_embeddings([question], user_reference=str(user_id)))[0]
        matches = await self.pinecone_service.query_vectors(
            query_embedding,
            top_k=settings.CHAT_MAX_CONTEXT_CHUNKS,
            document_id=str(document.id),
            user_id=str(user_id),
        )
        if not matches:
            return []

        chunk_ids_in_rank_order: list[uuid.UUID] = []
        match_by_chunk_id: dict[uuid.UUID, VectorMatch] = {}
        for match in matches:
            chunk_id_value = match.metadata.get("chunk_id")
            if not isinstance(chunk_id_value, str):
                continue
            try:
                chunk_id = uuid.UUID(chunk_id_value)
            except ValueError:
                continue
            chunk_ids_in_rank_order.append(chunk_id)
            match_by_chunk_id[chunk_id] = match

        if not chunk_ids_in_rank_order:
            return []

        statement: Select[tuple[DocumentChunk]] = select(DocumentChunk).where(
            DocumentChunk.document_id == document.id,
            DocumentChunk.id.in_(chunk_ids_in_rank_order),
        )
        chunks = list((await self.session.scalars(statement)).all())
        chunk_by_id = {chunk.id: chunk for chunk in chunks}

        retrieved_chunks: list[RetrievedChunk] = []
        for rank, chunk_id in enumerate(chunk_ids_in_rank_order, start=1):
            chunk = chunk_by_id.get(chunk_id)
            match = match_by_chunk_id.get(chunk_id)
            if chunk is None or match is None:
                continue
            retrieved_chunks.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=min(max(match.score, 0.0), 1.0),
                    source_rank=rank,
                )
            )
        return retrieved_chunks

    def _build_prompt(
        self,
        *,
        session: ChatSession,
        document: Document,
        question: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> str:
        conversation_history = [
            (message.role, message.content)
            for message in sorted(session.messages, key=lambda item: item.created_at)
            if message.role in {"user", "assistant"}
        ]
        context_sections = [
            self._format_context_section(item)
            for item in retrieved_chunks
        ]
        return self.llm_service.build_prompt(
            question=question,
            document_title=document.title,
            conversation_history=conversation_history,
            context_sections=context_sections,
        )

    async def _create_assistant_message(
        self,
        *,
        session: ChatSession,
        generated_answer: GeneratedAnswer,
        retrieved_chunks: list[RetrievedChunk],
        message_id: uuid.UUID | None = None,
    ) -> ChatMessage:
        now = utc_now()
        usage = generated_answer.usage
        prompt_tokens = usage.input_tokens if usage is not None else None
        completion_tokens = usage.output_tokens if usage is not None else None
        total_tokens = usage.total_tokens if usage is not None else None

        assistant_message = ChatMessage(
            id=message_id or uuid.uuid4(),
            chat_session_id=session.id,
            role="assistant",
            content=generated_answer.content,
            llm_model=generated_answer.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            created_at=now,
        )
        source_rows = [
            MessageSource(
                message_id=assistant_message.id,
                chunk_id=item.chunk.id,
                source_rank=item.source_rank,
                similarity_score=item.score,
                page_number_start=item.chunk.page_number_start,
                page_number_end=item.chunk.page_number_end,
                quoted_text=self._quoted_text(item.chunk.chunk_text),
                created_at=now,
            )
            for item in retrieved_chunks
        ]
        usage_log = UsageLog(
            id=uuid.uuid4(),
            user_id=session.user_id,
            document_id=session.document_id,
            session_id=session.id,
            action_type="chat_completion",
            provider="openai",
            model_name=generated_answer.model_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=Decimal("0"),
            created_at=now,
        )

        session.last_message_at = now
        session.updated_at = now
        try:
            self.session.add(assistant_message)
            if source_rows:
                self.session.add_all(source_rows)
            self.session.add(usage_log)
            await self.session.commit()
            await self.session.refresh(assistant_message)
            await self.session.refresh(assistant_message, attribute_names=["sources"])
            return assistant_message
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Failed to persist assistant message for chat session '%s'.", session.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to save the assistant response",
            ) from exc

    def _format_context_section(self, item: RetrievedChunk) -> str:
        page_start = item.chunk.page_number_start or "?"
        page_end = item.chunk.page_number_end or page_start
        return (
            f"Source rank: {item.source_rank}\n"
            f"Pages: {page_start}-{page_end}\n"
            f"Similarity: {item.score:.3f}\n"
            "Excerpt:\n"
            f"{item.chunk.chunk_text.strip()}"
        )

    def _quoted_text(self, chunk_text: str) -> str:
        normalized = " ".join(chunk_text.split())
        if len(normalized) <= 400:
            return normalized
        return f"{normalized[:397]}..."

    def _sse_event(self, event_name: str, payload: dict[str, object]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload, default=str)}\n\n"

    def _to_session_summary_response(self, session: ChatSession) -> ChatSessionSummaryResponse:
        return ChatSessionSummaryResponse.model_validate(session)

    def _to_session_response(self, session: ChatSession) -> ChatSessionResponse:
        ordered_messages = sorted(session.messages, key=lambda item: item.created_at)
        return ChatSessionResponse(
            id=session.id,
            user_id=session.user_id,
            document_id=session.document_id,
            title=session.title,
            status=session.status,
            started_at=session.started_at,
            last_message_at=session.last_message_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[self._to_message_response(message) for message in ordered_messages],
        )

    def _to_message_response(self, message: ChatMessage) -> ChatMessageResponse:
        ordered_sources: list[MessageSource]
        if "sources" in inspect(message).unloaded:
            ordered_sources = []
        else:
            ordered_sources = sorted(message.sources, key=lambda item: item.source_rank or 0)
        return ChatMessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            llm_model=message.llm_model,
            prompt_tokens=message.prompt_tokens,
            completion_tokens=message.completion_tokens,
            total_tokens=message.total_tokens,
            created_at=message.created_at,
            sources=[
                ChatSourceResponse(
                    chunk_id=source.chunk_id,
                    source_rank=source.source_rank,
                    similarity_score=source.similarity_score,
                    page_number_start=source.page_number_start,
                    page_number_end=source.page_number_end,
                    quoted_text=source.quoted_text,
                )
                for source in ordered_sources
            ],
        )

    def _source_payload(self, item: RetrievedChunk) -> dict[str, object]:
        return {
            "chunk_id": str(item.chunk.id),
            "source_rank": item.source_rank,
            "similarity_score": item.score,
            "page_number_start": item.chunk.page_number_start,
            "page_number_end": item.chunk.page_number_end,
            "quoted_text": self._quoted_text(item.chunk.chunk_text),
        }

    def _message_payload(self, message: ChatMessage) -> dict[str, object]:
        response = self._to_message_response(message)
        return response.model_dump(mode="json")
