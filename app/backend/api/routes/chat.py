import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.api.auth_dependencies import CurrentAuthContext
from app.db import get_db_session
from app.logger import get_logger
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=ChatSessionListResponse)
async def list_chats(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionListResponse:
    """
    List chat sessions for the current authenticated user.

    This endpoint returns the authenticated user's persisted chat sessions in
    reverse chronological order. Only chat sessions owned by the caller are
    included, and the response is intended to support chat history listings
    in client applications.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        A list of chat sessions owned by the authenticated user.

    Raises:
        HTTPException: Returned when the chat sessions cannot be loaded or an
            unexpected server-side error occurs.
    """
    try:
        service = ChatService(session)
        return ChatSessionListResponse(items=await service.list_sessions(auth_context.user.id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception while listing chat sessions for user '%s'.", auth_context.user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load chat sessions at the moment",
        ) from exc


@router.post(
    "/",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: ChatSessionCreate,
) -> ChatSessionResponse:
    """
    Create a new chat session for a processed document.

    This endpoint creates a persistent chat session scoped to a single
    uploaded document owned by the authenticated user. The target document
    must already be fully processed so that retrieval and question-answering
    can be performed against its stored chunks and vectors.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.
        payload: Request payload containing the target document identifier and
            optional chat title override.

    Returns:
        The newly created chat session metadata.

    Raises:
        HTTPException: Returned when the document does not exist, does not
            belong to the authenticated user, is not ready for chat, or the
            chat session cannot be created.
    """
    try:
        service = ChatService(session)
        response = await service.create_session(auth_context.user.id, payload)
        logger.info(
            "Created chat session '%s' for authenticated user '%s'.",
            response.id,
            auth_context.user.id,
        )
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled exception while creating a chat session for user '%s'.", auth_context.user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create a chat session at the moment",
        ) from exc


@router.get("/{chat_id}", response_model=ChatSessionResponse)
async def get_chat(
    chat_id: uuid.UUID,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionResponse:
    """
    Load a single chat session owned by the authenticated user.

    This endpoint resolves one persisted chat session by identifier and
    returns its metadata together with the stored message history. Ownership
    is enforced through the authenticated user context so callers can only
    access their own chat sessions.

    Args:
        chat_id: Unique identifier of the chat session to load.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        The requested chat session with its persisted messages and any saved
        source metadata associated with assistant answers.

    Raises:
        HTTPException: Returned when the chat session does not exist, is not
            owned by the authenticated user, or cannot be loaded.
    """
    try:
        service = ChatService(session)
        chat_session = await service.get_session(auth_context.user.id, chat_id)
        if not chat_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
        return chat_session
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled exception while loading chat session '%s' for user '%s'.",
            chat_id,
            auth_context.user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load the requested chat session at the moment",
        ) from exc


@router.post(
    "/{chat_id}/messages",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    chat_id: uuid.UUID,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: ChatMessageCreate,
) -> ChatSessionResponse:
    """
    Submit a user message and generate a document-grounded assistant reply.

    This endpoint runs the full chat pipeline for an existing chat session:
    it validates chat ownership, embeds the incoming user question, retrieves
    similar document chunks from Pinecone, loads those chunks from PostgreSQL,
    builds grounded context, requests an answer from the configured OpenAI
    chat model, persists the user and assistant messages, stores source
    references, and records usage metadata for the exchange.

    Args:
        chat_id: Unique identifier of the target chat session.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.
        payload: Incoming user message payload containing the question content
            and optional model override.

    Returns:
        The updated chat session including the newly persisted user message,
        assistant response, and any retrieved source citations.

    Raises:
        HTTPException: Returned when the chat session does not exist, is not
            owned by the authenticated user, is inactive, is linked to a
            document that is not ready for chat, or the retrieval/answering
            pipeline fails.
    """
    try:
        service = ChatService(session)
        chat_session = await service.add_message(
            user_id=auth_context.user.id,
            session_id=chat_id,
            payload=payload,
        )
        if not chat_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
        logger.info(
            "Completed chat answer generation for session '%s' and user '%s'.",
            chat_id,
            auth_context.user.id,
        )
        return chat_session
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled exception while generating a chat response for session '%s' and user '%s'.",
            chat_id,
            auth_context.user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to generate a chat response at the moment",
        ) from exc
