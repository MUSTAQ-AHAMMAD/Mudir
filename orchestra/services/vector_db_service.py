"""Vector DB service — long-term memory backed by ChromaDB.

Connects to a running ChromaDB server (``localhost:8000`` by default) and
stores/searches embeddings in the ``orchestra_memory`` collection. Falls back to
generating embeddings via :mod:`embeddings_service` when a caller stores or
searches with raw text and no precomputed vector.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Sequence

from .config import config, get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    import chromadb

_log = get_logger(__name__)


class VectorDBServiceError(RuntimeError):
    """Raised when a vector database operation fails."""


class VectorDBService:
    """Client for the ChromaDB ``orchestra_memory`` collection."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection: Optional[str] = None,
    ) -> None:
        self.host = host or config.chroma_host
        self.port = port or config.chroma_port
        self.collection_name = collection or config.chroma_collection
        self._client: Optional["chromadb.api.ClientAPI"] = None
        self._collection: Any = None

    # -- connection ---------------------------------------------------------
    @property
    def collection(self) -> Any:
        """Lazily connect to ChromaDB and return the target collection."""

        if self._collection is None:
            try:
                import chromadb
            except ImportError as exc:  # pragma: no cover
                raise VectorDBServiceError(
                    "chromadb is not installed; see requirements.txt"
                ) from exc
            try:
                self._client = chromadb.HttpClient(host=self.host, port=self.port)
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                _log.info(
                    "Connected to ChromaDB %s:%s collection=%s",
                    self.host,
                    self.port,
                    self.collection_name,
                )
            except Exception as exc:  # noqa: BLE001
                raise VectorDBServiceError(
                    f"Could not connect to ChromaDB at {self.host}:{self.port}: {exc}"
                ) from exc
        return self._collection

    def health_check(self) -> bool:
        """Return ``True`` when the ChromaDB server heartbeat responds."""

        try:
            import chromadb

            client = self._client or chromadb.HttpClient(host=self.host, port=self.port)
            client.heartbeat()
            return True
        except Exception as exc:  # noqa: BLE001
            _log.warning("ChromaDB health check failed: %s", exc)
            return False

    # -- CRUD ---------------------------------------------------------------
    def store(
        self,
        id: str,  # noqa: A002 - matches the requested public API
        text: str,
        metadata: Optional[dict[str, Any]] = None,
        embedding: Optional[Sequence[float]] = None,
    ) -> None:
        """Store (or upsert) a document, its metadata and its embedding.

        If ``embedding`` is omitted it is generated from ``text`` via the
        embeddings service.
        """

        if not id:
            raise VectorDBServiceError("id must be a non-empty string")
        vector = list(embedding) if embedding is not None else self._embed(text)
        try:
            self.collection.upsert(
                ids=[id],
                documents=[text],
                metadatas=[metadata or {}],
                embeddings=[vector],
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorDBServiceError(f"Failed to store id={id!r}: {exc}") from exc

    def search(
        self,
        query_embedding: Sequence[float],
        limit: int = 10,
        where: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Search the collection by vector similarity.

        Returns a list of ``{"id", "text", "metadata", "distance"}`` dicts,
        ordered from most to least similar.
        """

        try:
            result = self.collection.query(
                query_embeddings=[list(query_embedding)],
                n_results=limit,
                where=where,
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorDBServiceError(f"Search failed: {exc}") from exc
        return self._flatten_query(result)

    def search_text(self, text: str, limit: int = 10) -> list[dict[str, Any]]:
        """Convenience search that embeds ``text`` before querying."""

        return self.search(self._embed(text), limit=limit)

    def get_by_id(self, id: str) -> Optional[dict[str, Any]]:  # noqa: A002
        """Retrieve a single entry by id, or ``None`` if it does not exist."""

        try:
            result = self.collection.get(ids=[id], include=["documents", "metadatas"])
        except Exception as exc:  # noqa: BLE001
            raise VectorDBServiceError(f"get_by_id failed for {id!r}: {exc}") from exc
        ids = result.get("ids") or []
        if not ids:
            return None
        docs = result.get("documents") or [None]
        metas = result.get("metadatas") or [None]
        return {"id": ids[0], "text": docs[0], "metadata": metas[0]}

    def delete(self, id: str) -> None:  # noqa: A002
        """Delete an entry by id (no-op if it does not exist)."""

        try:
            self.collection.delete(ids=[id])
        except Exception as exc:  # noqa: BLE001
            raise VectorDBServiceError(f"delete failed for {id!r}: {exc}") from exc

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _embed(text: str) -> list[float]:
        from .embeddings_service import generate_embedding

        return generate_embedding(text)

    @staticmethod
    def _flatten_query(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten ChromaDB's nested (batched) query response into row dicts."""

        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        rows: list[dict[str, Any]] = []
        for i, _id in enumerate(ids):
            rows.append(
                {
                    "id": _id,
                    "text": docs[i] if i < len(docs) else None,
                    "metadata": metas[i] if i < len(metas) else None,
                    "distance": dists[i] if i < len(dists) else None,
                }
            )
        return rows


# Module-level singleton and functional wrappers.
_default_service: Optional[VectorDBService] = None


def get_service() -> VectorDBService:
    """Return a lazily-instantiated shared :class:`VectorDBService`."""

    global _default_service
    if _default_service is None:
        _default_service = VectorDBService()
    return _default_service


def store(
    id: str,  # noqa: A002
    text: str,
    metadata: Optional[dict[str, Any]] = None,
    embedding: Optional[Sequence[float]] = None,
) -> None:
    """Module-level wrapper around :meth:`VectorDBService.store`."""

    return get_service().store(id, text, metadata, embedding)


def search(query_embedding: Sequence[float], limit: int = 10) -> list[dict[str, Any]]:
    """Module-level wrapper around :meth:`VectorDBService.search`."""

    return get_service().search(query_embedding, limit=limit)


def get_by_id(id: str) -> Optional[dict[str, Any]]:  # noqa: A002
    """Module-level wrapper around :meth:`VectorDBService.get_by_id`."""

    return get_service().get_by_id(id)


def delete(id: str) -> None:  # noqa: A002
    """Module-level wrapper around :meth:`VectorDBService.delete`."""

    return get_service().delete(id)


__all__ = [
    "VectorDBService",
    "VectorDBServiceError",
    "get_service",
    "store",
    "search",
    "get_by_id",
    "delete",
]
