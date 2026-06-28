import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.api.auth_dependencies import CurrentAuthContext
from app.db import get_db_session
from app.logger import get_logger
from app.schemas.chat import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatTurnResponse,
)
from app.services.chat_service import ChatService

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    summary="List chat sessions for the authenticated user",
    description=(
        "Return the current user's chat sessions ordered by most recently updated. "
        "Each session is scoped to the authenticated account and its linked document."
    ),
)
async def list_sessions(
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionListResponse:
    """
    List all chat sessions owned by the authenticated user.

    This endpoint returns lightweight session metadata for the current caller.
    It is intended for rendering a chat-session sidebar or resuming a previous
    document conversation.

    Args:
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        A list of chat-session summaries belonging to the authenticated user.

    Raises:
        HTTPException: Returned when chat sessions cannot be loaded.
    """
    try:
        service = ChatService(session)
        response = ChatSessionListResponse(items=await service.list_sessions(auth_context.user.id))
        logger.info("Listed chat sessions for authenticated user '%s'.", auth_context.user.id)
        return response
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
    summary="Create a chat session for a processed document",
    description=(
        "Create a new authenticated chat session bound to a single uploaded document. "
        "The document must belong to the current user."
    ),
)
async def create_session(
    payload: ChatSessionCreate,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionResponse:
    """
    Create a new document-scoped chat session.

    This endpoint initializes a persistent chat session associated with one of
    the authenticated user's uploaded documents. The created session can then
    be used for both non-streaming and streaming question-answer turns.

    Args:
        payload: Chat-session creation payload containing the target document ID.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        The newly created chat session, including its current message list.

    Raises:
        HTTPException: Returned when the document does not exist, does not
            belong to the user, or the session cannot be created.
    """
    try:
        service = ChatService(session)
        response = await service.create_session(auth_context.user.id, payload)
        logger.info(
            "Created chat session '%s' for authenticated user '%s' and document '%s'.",
            response.id,
            auth_context.user.id,
            response.document_id,
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


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Get one chat session with message history",
    description=(
        "Load a single authenticated chat session and its persisted messages. "
        "Access is limited to sessions owned by the current user."
    ),
)
async def get_session(
    session_id: uuid.UUID,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatSessionResponse:
    """
    Load a single chat session for the authenticated user.

    This endpoint returns the full message history for one document-specific
    session so a client can restore a previous conversation view.

    Args:
        session_id: Unique identifier of the chat session to load.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        The requested chat session together with its message history.

    Raises:
        HTTPException: Returned when the session does not exist or cannot be loaded.
    """
    try:
        service = ChatService(session)
        chat_session = await service.get_session(auth_context.user.id, session_id)
        if not chat_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        logger.info("Loaded chat session '%s' for authenticated user '%s'.", session_id, auth_context.user.id)
        return chat_session
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled exception while loading chat session '%s' for user '%s'.",
            session_id,
            auth_context.user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load the requested chat session at the moment",
        ) from exc


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatTurnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a question and return a complete assistant answer",
    description=(
        "Persist a user message, retrieve relevant document chunks, generate a grounded "
        "assistant response, and return the completed chat turn in one response."
    ),
)
async def add_message(
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatTurnResponse:
    """
    Process a non-streaming RAG chat turn for the authenticated user.

    This endpoint stores the caller's question, retrieves matching chunks from
    the linked document, sends the grounded prompt to the LLM, persists the
    assistant reply, and returns both sides of the completed turn.

    Args:
        session_id: Unique identifier of the chat session receiving the message.
        payload: User question payload, with an optional model override.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        The updated session together with the persisted user and assistant messages.

    Raises:
        HTTPException: Returned when the session or document is unavailable, the
            document is not ready for chat, or answer generation fails.
    """
    try:
        service = ChatService(session)
        response = await service.answer_question(
            user_id=auth_context.user.id,
            session_id=session_id,
            payload=payload,
        )
        logger.info(
            "Completed non-streaming chat turn for session '%s' and user '%s'.",
            session_id,
            auth_context.user.id,
        )
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled exception while processing non-streaming chat turn for session '%s' and user '%s'.",
            session_id,
            auth_context.user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process the chat message at the moment",
        ) from exc


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Submit a question and stream the assistant answer",
    description=(
        "Persist a user message and stream the assistant response incrementally over "
        "Server-Sent Events while the backend performs retrieval and generation."
    ),
)
async def stream_message(
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    auth_context: CurrentAuthContext,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StreamingResponse:
    """
    Stream a grounded assistant answer over Server-Sent Events.

    This endpoint is the production chat transport for real-time UX. It stores
    the incoming user message, performs retrieval against the associated
    document, and streams assistant text deltas as SSE events until completion.

    Args:
        session_id: Unique identifier of the chat session receiving the message.
        payload: User question payload, with an optional model override.
        auth_context: Authenticated request context resolved from the bearer token.
        session: Async database session injected by FastAPI.

    Returns:
        A `text/event-stream` response that emits chat lifecycle and token-delta events.

    Raises:
        HTTPException: Returned when the session or document is unavailable or
            when the streaming response cannot be initialized.
    """
    try:
        service = ChatService(session)
        logger.info(
            "Starting streaming chat turn for session '%s' and user '%s'.",
            session_id,
            auth_context.user.id,
        )
        return StreamingResponse(
            service.stream_answer(
                user_id=auth_context.user.id,
                session_id=session_id,
                payload=payload,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled exception while starting streaming chat turn for session '%s' and user '%s'.",
            session_id,
            auth_context.user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to start streaming the assistant response at the moment",
        ) from exc
