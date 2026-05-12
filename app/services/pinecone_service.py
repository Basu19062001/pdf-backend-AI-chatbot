from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import HTTPException, status
from pinecone import Pinecone, PineconeException, ServerlessSpec

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_pinecone_client: Pinecone | None = None
_pinecone_index_host: str | None = None


@dataclass(slots=True)
class VectorRecord:
    vector_id: str
    values: list[float]
    metadata: dict[str, str | int | float | bool | list[str] | list[int] | list[float]]


@dataclass(slots=True)
class QueryMatch:
    vector_id: str
    score: float
    metadata: dict[str, str | int | float | bool | list[str] | list[int] | list[float]]


class PineconeService:
    """Manage Pinecone index lifecycle and vector operations."""

    def _get_client(self) -> Pinecone:
        global _pinecone_client

        if _pinecone_client is None:
            api_key = settings.PINECONE_API_KEY.strip()
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Pinecone is not configured on the server",
                )
            _pinecone_client = Pinecone(api_key=api_key)
            logger.info("Initialized Pinecone client for index '%s'.", settings.PINECONE_INDEX_NAME)
        return _pinecone_client

    def _resolve_index_host(self) -> str:
        global _pinecone_index_host

        configured_host = settings.PINECONE_INDEX_HOST.strip()
        if configured_host:
            return configured_host

        if _pinecone_index_host is not None:
            return _pinecone_index_host

        client = self._get_client()
        index_name = settings.PINECONE_INDEX_NAME.strip()
        if not index_name:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Pinecone index name is not configured on the server",
            )

        try:
            if not client.has_index(index_name):
                if not settings.PINECONE_CREATE_INDEX_IF_MISSING:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Pinecone index is not available",
                    )

                logger.info(
                    "Creating Pinecone index '%s'. cloud='%s' region='%s' dimension=%s metric='%s'",
                    index_name,
                    settings.PINECONE_CLOUD,
                    settings.PINECONE_REGION,
                    settings.EMBEDDING_DIMENSION,
                    settings.PINECONE_METRIC,
                )
                client.create_index(
                    name=index_name,
                    dimension=settings.EMBEDDING_DIMENSION,
                    metric=settings.PINECONE_METRIC,
                    spec=ServerlessSpec(
                        cloud=settings.PINECONE_CLOUD,
                        region=settings.PINECONE_REGION,
                    ),
                    timeout=settings.PINECONE_INDEX_TIMEOUT_SECONDS,
                    tags={
                        "app": "pdf-chatbot",
                        "environment": settings.ENVIRONMENT,
                        "embedding_model": settings.EMBEDDING_MODEL,
                    },
                )

            description = client.describe_index(index_name)
            _pinecone_index_host = description.host
            logger.info(
                "Resolved Pinecone index host for '%s'. host='%s'",
                index_name,
                _pinecone_index_host,
            )
            return _pinecone_index_host
        except HTTPException:
            raise
        except PineconeException as exc:
            logger.exception("Failed to initialize Pinecone index '%s'.", index_name)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to initialize Pinecone index",
            ) from exc

    def _namespace(self) -> str | None:
        namespace = settings.PINECONE_NAMESPACE.strip()
        return namespace or None

    def _get_index(self):
        client = self._get_client()
        host = self._resolve_index_host()
        return client.Index(host=host)

    async def upsert_vectors(self, records: Sequence[VectorRecord]) -> None:
        if not records:
            return
        await asyncio.to_thread(self._upsert_vectors_sync, list(records))

    def _upsert_vectors_sync(self, records: list[VectorRecord]) -> None:
        try:
            index = self._get_index()
            payload = [
                {
                    "id": record.vector_id,
                    "values": record.values,
                    "metadata": record.metadata,
                }
                for record in records
            ]
            logger.info(
                "Upserting vectors into Pinecone. vector_count=%s index='%s' namespace='%s'",
                len(payload),
                settings.PINECONE_INDEX_NAME,
                self._namespace() or "<default>",
            )
            index.upsert(
                vectors=payload,
                namespace=self._namespace(),
                batch_size=settings.PINECONE_UPSERT_BATCH_SIZE,
                show_progress=False,
            )
            logger.info(
                "Pinecone upsert completed successfully. vector_count=%s index='%s'",
                len(payload),
                settings.PINECONE_INDEX_NAME,
            )
        except PineconeException as exc:
            logger.exception("Pinecone upsert failed for index '%s'.", settings.PINECONE_INDEX_NAME)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to upsert document vectors to Pinecone",
            ) from exc

    async def delete_vectors(self, vector_ids: Sequence[str]) -> None:
        if not vector_ids:
            return
        await asyncio.to_thread(self._delete_vectors_sync, list(vector_ids))

    async def query_similar(
        self,
        vector: Sequence[float],
        top_k: int,
        metadata_filter: dict[str, object] | None = None,
    ) -> list[QueryMatch]:
        if not vector:
            return []
        return await asyncio.to_thread(
            self._query_similar_sync,
            list(vector),
            top_k,
            metadata_filter,
        )

    def _query_similar_sync(
        self,
        vector: list[float],
        top_k: int,
        metadata_filter: dict[str, object] | None,
    ) -> list[QueryMatch]:
        try:
            index = self._get_index()
            logger.info(
                "Querying Pinecone for similar chunks. top_k=%s index='%s' namespace='%s'",
                top_k,
                settings.PINECONE_INDEX_NAME,
                self._namespace() or "<default>",
            )
            response = index.query(
                vector=vector,
                top_k=top_k,
                namespace=self._namespace(),
                include_metadata=True,
                filter=metadata_filter,
            )
            matches = getattr(response, "matches", None) or []
            return [
                QueryMatch(
                    vector_id=match.id,
                    score=float(match.score or 0.0),
                    metadata=dict(match.metadata or {}),
                )
                for match in matches
            ]
        except PineconeException as exc:
            logger.exception("Pinecone similarity search failed for index '%s'.", settings.PINECONE_INDEX_NAME)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to retrieve similar document chunks from Pinecone",
            ) from exc

    def _delete_vectors_sync(self, vector_ids: list[str]) -> None:
        try:
            index = self._get_index()
            logger.info(
                "Deleting vectors from Pinecone. vector_count=%s index='%s' namespace='%s'",
                len(vector_ids),
                settings.PINECONE_INDEX_NAME,
                self._namespace() or "<default>",
            )
            index.delete(ids=vector_ids, namespace=self._namespace())
        except PineconeException:
            logger.exception(
                "Best-effort Pinecone cleanup failed. index='%s' vector_count=%s",
                settings.PINECONE_INDEX_NAME,
                len(vector_ids),
            )
