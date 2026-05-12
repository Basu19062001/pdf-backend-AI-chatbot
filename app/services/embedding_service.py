from __future__ import annotations

from collections.abc import Sequence

from fastapi import HTTPException, status
from openai import APIConnectionError, AsyncOpenAI, OpenAIError, RateLimitError

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_openai_client: AsyncOpenAI | None = None


class EmbeddingService:
    """Create embeddings for chunk text using the OpenAI Embeddings API."""

    def _get_client(self) -> AsyncOpenAI:
        global _openai_client

        if _openai_client is None:
            api_key = settings.OPENAI_API_KEY.strip()
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="OpenAI embedding service is not configured on the server",
                )
            _openai_client = AsyncOpenAI(api_key=api_key)
            logger.info("Initialized OpenAI embedding client. model='%s'", settings.EMBEDDING_MODEL)
        return _openai_client

    async def create_embeddings(self, texts: Sequence[str], user_reference: str | None = None) -> list[list[float]]:
        normalized_texts = [text.strip() for text in texts if text and text.strip()]
        if not normalized_texts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one non-empty text chunk is required for embedding generation",
            )

        client = self._get_client()
        embeddings: list[list[float]] = []

        logger.info(
            "Requesting OpenAI embeddings. chunks=%s batch_size=%s model='%s'",
            len(normalized_texts),
            settings.EMBEDDING_BATCH_SIZE,
            settings.EMBEDDING_MODEL,
        )

        try:
            for batch_start in range(0, len(normalized_texts), settings.EMBEDDING_BATCH_SIZE):
                batch = normalized_texts[batch_start : batch_start + settings.EMBEDDING_BATCH_SIZE]
                request_kwargs: dict[str, object] = {
                    "input": batch,
                    "model": settings.EMBEDDING_MODEL,
                    "dimensions": settings.EMBEDDING_DIMENSION,
                    "encoding_format": "float",
                    "timeout": settings.OPENAI_EMBEDDING_TIMEOUT_SECONDS,
                }
                if user_reference:
                    request_kwargs["user"] = user_reference

                response = await client.embeddings.create(**request_kwargs)
                for item in sorted(response.data, key=lambda entry: entry.index):
                    if len(item.embedding) != settings.EMBEDDING_DIMENSION:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="OpenAI returned an embedding with an unexpected dimension",
                        )
                    embeddings.append(item.embedding)

            if len(embeddings) != len(normalized_texts):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="OpenAI returned an incomplete embedding response",
                )

            logger.info(
                "OpenAI embeddings completed successfully. chunks=%s model='%s' dimension=%s",
                len(embeddings),
                settings.EMBEDDING_MODEL,
                settings.EMBEDDING_DIMENSION,
            )
            return embeddings
        except HTTPException:
            raise
        except RateLimitError as exc:
            logger.warning("OpenAI embedding rate limit exceeded. model='%s'", settings.EMBEDDING_MODEL)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI embedding service rate limit exceeded",
            ) from exc
        except APIConnectionError as exc:
            logger.exception("Unable to reach OpenAI embedding service.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to reach OpenAI embedding service",
            ) from exc
        except OpenAIError as exc:
            logger.exception("OpenAI embedding request failed. model='%s'", settings.EMBEDDING_MODEL)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI embedding request failed",
            ) from exc
