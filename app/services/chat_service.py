from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, select
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
    ChatMessageSourceResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.pinecone_service import PineconeService, QueryMatch
from app.utils import utc_now

logger = get_logger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float
    rank: int


class ChatService:
    """Persist chat sessions and run retrieval-augmented answers over uploaded documents."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = EmbeddingService()
        self.pinecone_service = PineconeService()
        self.llm_service = LLMService()

    async def list_sessions(self, user_id: uuid.UUID) -> list[ChatSessionResponse]:
        try:
            statement: Select[tuple[ChatSession]] = (
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
            )
            sessions = list((await self.session.scalars(statement)).all())
            return [self._build_session_response(session, include_messages=False) for session in sessions]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list chat sessions for user '%s'.", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load chat sessions at the moment",
            ) from exc

    async def create_session(self, user_id: uuid.UUID, payload: ChatSessionCreate) -> ChatSessionResponse:
        document = await self._load_chat_ready_document(user_id, payload.document_id)
        session_title = payload.title or document.title or document.original_file_name
        session_row = ChatSession(
            user_id=user_id,
            document_id=document.id,
            title=session_title,
            status="active",
            started_at=utc_now(),
        )
        self.session.add(session_row)
        try:
            await self.session.commit()
            await self.session.refresh(session_row)
            logger.info(
                "Created chat session '%s' for user '%s' and document '%s'.",
                session_row.id,
                user_id,
                document.id,
            )
            return self._build_session_response(session_row, include_messages=False)
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Failed to create chat session for user '%s' and document '%s'.", user_id, document.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to create a chat session at the moment",
            ) from exc

    async def get_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSessionResponse | None:
        try:
            session_row = await self._load_owned_session(user_id, session_id)
            if session_row is None:
                return None
            return self._build_session_response(session_row, include_messages=True)
        except SQLAlchemyError as exc:
            logger.exception("Failed to load chat session '%s' for user '%s'.", session_id, user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to load the requested chat session at the moment",
            ) from exc

    async def add_message(self, user_id: uuid.UUID, session_id: uuid.UUID, payload: ChatMessageCreate) -> ChatSessionResponse | None:
        if payload.role != "user":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only user messages can be submitted to this endpoint",
            )

        session_row = await self._load_owned_session(user_id, session_id)
        if session_row is None:
            return None
        if session_row.status != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only active chat sessions can accept new messages",
            )
        if session_row.document.status != "processed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The linked document is not ready for chat yet",
            )

        question = payload.content.strip()
        user_message = ChatMessage(
            chat_session_id=session_row.id,
            role="user",
            content=question,
        )
        now = utc_now()

        try:
            question_embedding = (
                await self.embedding_service.create_embeddings([question], user_reference=str(user_id))
            )[0]
            retrieved_chunks = await self._retrieve_similar_chunks(
                user_id=user_id,
                document_id=session_row.document_id,
                question_embedding=question_embedding,
            )
            answer = await self.llm_service.answer_question(
                question=question,
                context_blocks=self._build_context_blocks(retrieved_chunks),
                conversation_history=self._build_conversation_history(session_row.messages),
                model_name=payload.model_name,
                user_reference=str(user_id),
            )
            assistant_message = ChatMessage(
                chat_session_id=session_row.id,
                role="assistant",
                content=answer.text,
                llm_model=answer.model_name,
                prompt_tokens=answer.prompt_tokens,
                completion_tokens=answer.completion_tokens,
                total_tokens=answer.total_tokens,
                estimated_cost=self._estimate_cost(answer.prompt_tokens, answer.completion_tokens),
            )

            self.session.add(user_message)
            self.session.add(assistant_message)
            await self.session.flush()

            self.session.add_all(self._build_source_records(assistant_message.id, retrieved_chunks))
            self.session.add(
                UsageLog(
                    user_id=user_id,
                    document_id=session_row.document_id,
                    session_id=session_row.id,
                    action_type="chat_completion",
                    provider="openai",
                    model_name=answer.model_name,
                    input_tokens=answer.prompt_tokens,
                    output_tokens=answer.completion_tokens,
                    total_tokens=answer.total_tokens,
                    cost=assistant_message.estimated_cost,
                )
            )

            session_row.last_message_at = now
            session_row.updated_at = now
            await self.session.commit()
            logger.info(
                "Persisted chat exchange for session '%s'. retrieved_chunks=%s model='%s'",
                session_row.id,
                len(retrieved_chunks),
                answer.model_name,
            )
        except HTTPException:
            await self.session.rollback()
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            logger.exception("Failed to persist chat exchange for session '%s'.", session_row.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to save the chat exchange at the moment",
            ) from exc

        return await self.get_session(user_id, session_id)

    async def _load_chat_ready_document(self, user_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        statement: Select[tuple[Document]] = select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        document = await self.session.scalar(statement)
        logger.debug(f"document: {statement} | {document}")
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        if document.status != "processed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document processing is not complete yet",
            )
        return document

    async def _load_owned_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession | None:
        statement: Select[tuple[ChatSession]] = (
            select(ChatSession)
            .options(
                selectinload(ChatSession.document),
                selectinload(ChatSession.messages)
                .selectinload(ChatMessage.sources)
                .selectinload(MessageSource.chunk),
            )
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
        )
        return await self.session.scalar(statement)

    async def _retrieve_similar_chunks(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID,
        question_embedding: list[float],
    ) -> list[RetrievedChunk]:
        matches = await self.pinecone_service.query_similar(
            vector=question_embedding,
            top_k=settings.CHAT_RETRIEVAL_TOP_K,
            metadata_filter={
                "user_id": {"$eq": str(user_id)},
                "document_id": {"$eq": str(document_id)},
            },
        )
        if not matches:
            return []

        chunk_ids_in_rank_order: list[uuid.UUID] = []
        match_by_chunk_id: dict[uuid.UUID, QueryMatch] = {}
        for match in matches:
            raw_chunk_id = match.metadata.get("chunk_id")
            if not raw_chunk_id:
                continue
            chunk_id = uuid.UUID(str(raw_chunk_id))
            chunk_ids_in_rank_order.append(chunk_id)
            match_by_chunk_id[chunk_id] = match

        if not chunk_ids_in_rank_order:
            return []

        chunk_statement: Select[tuple[DocumentChunk]] = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.id.in_(chunk_ids_in_rank_order),
        )
        chunk_rows = list((await self.session.scalars(chunk_statement)).all())
        chunks_by_id = {chunk.id: chunk for chunk in chunk_rows}

        retrieved_chunks: list[RetrievedChunk] = []
        for index, chunk_id in enumerate(chunk_ids_in_rank_order, start=1):
            chunk = chunks_by_id.get(chunk_id)
            match = match_by_chunk_id.get(chunk_id)
            if chunk is None or match is None:
                continue
            retrieved_chunks.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=match.score,
                    rank=index,
                )
            )
        return retrieved_chunks

    def _build_conversation_history(self, messages: list[ChatMessage]) -> list[tuple[str, str]]:
        ordered_messages = sorted(messages, key=lambda item: item.created_at)
        if settings.CHAT_HISTORY_MESSAGE_LIMIT == 0:
            return []
        recent_messages = ordered_messages[-settings.CHAT_HISTORY_MESSAGE_LIMIT :]
        return [(message.role, message.content) for message in recent_messages]

    def _build_context_blocks(self, retrieved_chunks: list[RetrievedChunk]) -> list[str]:
        if not retrieved_chunks:
            return []

        context_blocks: list[str] = []
        consumed_characters = 0
        for retrieved_chunk in retrieved_chunks:
            page_start = retrieved_chunk.chunk.page_number_start or "?"
            page_end = retrieved_chunk.chunk.page_number_end or page_start
            context_block = (
                f"[Source {retrieved_chunk.rank} | pages {page_start}-{page_end} | score {retrieved_chunk.score:.4f}]\n"
                f"{retrieved_chunk.chunk.chunk_text.strip()}"
            )
            block_length = len(context_block)
            if context_blocks and consumed_characters + block_length > settings.CHAT_MAX_CONTEXT_CHARACTERS:
                break
            if not context_blocks and block_length > settings.CHAT_MAX_CONTEXT_CHARACTERS:
                context_blocks.append(context_block[: settings.CHAT_MAX_CONTEXT_CHARACTERS])
                break
            context_blocks.append(context_block)
            consumed_characters += block_length
        return context_blocks

    def _build_source_records(self, message_id: uuid.UUID, retrieved_chunks: list[RetrievedChunk]) -> list[MessageSource]:
        source_records: list[MessageSource] = []
        for retrieved_chunk in retrieved_chunks:
            snippet = retrieved_chunk.chunk.chunk_text.strip()[: settings.CHAT_SOURCE_TEXT_MAX_CHARACTERS]
            source_records.append(
                MessageSource(
                    message_id=message_id,
                    chunk_id=retrieved_chunk.chunk.id,
                    source_rank=retrieved_chunk.rank,
                    similarity_score=retrieved_chunk.score,
                    page_number_start=retrieved_chunk.chunk.page_number_start,
                    page_number_end=retrieved_chunk.chunk.page_number_end,
                    quoted_text=snippet,
                )
            )
        return source_records

    def _estimate_cost(self, prompt_tokens: int | None, completion_tokens: int | None) -> Decimal | None:
        if prompt_tokens is None and completion_tokens is None:
            return None
        prompt_cost = (
            Decimal(prompt_tokens or 0)
            * Decimal(str(settings.OPENAI_CHAT_INPUT_COST_PER_1M_TOKENS))
            / Decimal(1_000_000)
        )
        completion_cost = (
            Decimal(completion_tokens or 0)
            * Decimal(str(settings.OPENAI_CHAT_OUTPUT_COST_PER_1M_TOKENS))
            / Decimal(1_000_000)
        )
        total_cost = prompt_cost + completion_cost
        return total_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _build_session_response(self, session_row: ChatSession, include_messages: bool) -> ChatSessionResponse:
        messages: list[ChatMessageResponse] = []
        if include_messages:
            ordered_messages = sorted(session_row.messages, key=lambda item: item.created_at)
            messages = [self._build_message_response(message) for message in ordered_messages]

        return ChatSessionResponse(
            id=session_row.id,
            user_id=session_row.user_id,
            document_id=session_row.document_id,
            title=session_row.title,
            status=session_row.status,
            started_at=session_row.started_at,
            last_message_at=session_row.last_message_at,
            created_at=session_row.created_at,
            updated_at=session_row.updated_at,
            messages=messages,
        )

    def _build_message_response(self, message: ChatMessage) -> ChatMessageResponse:
        ordered_sources = sorted(message.sources, key=lambda item: item.source_rank or 0)
        return ChatMessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            model_name=message.llm_model,
            prompt_tokens=message.prompt_tokens,
            completion_tokens=message.completion_tokens,
            total_tokens=message.total_tokens,
            estimated_cost=message.estimated_cost,
            created_at=message.created_at,
            sources=[
                ChatMessageSourceResponse(
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
