from chat_memory.config import settings

from chat_memory.services.embedding_service import EmbeddingService
from chat_memory.services.qdrant_service import QdrantService
from chat_memory.services.chunking_service import ChunkingService

# Lazy singletons — tidak diinisialisasi saat import,
# hanya dibuat pertama kali endpoint dipanggil.
_embedding_service: EmbeddingService | None = None
_qdrant_service: QdrantService | None = None
_chunking_service: ChunkingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(settings.embedding_model)
    return _embedding_service


def get_chunking_service() -> ChunkingService:
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ChunkingService(
            settings.chunk_size,
            settings.chunk_overlap,
        )
    return _chunking_service


def get_qdrant_service() -> QdrantService:
    global _qdrant_service
    if _qdrant_service is None:
        emb = get_embedding_service()
        vector_size = len(emb.embed("test"))
        _qdrant_service = QdrantService(
            settings.qdrant_host,
            settings.qdrant_port,
            settings.collection_name,
        )
        _qdrant_service.create_collection(vector_size)
    return _qdrant_service


# Alias untuk backward-compat (main.py import langsung nama ini)
class _LazyProxy:
    """Proxy yang forward semua call ke service yang di-lazy-load."""
    def __init__(self, getter):
        object.__setattr__(self, "_getter", getter)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_getter")(), name)


embedding_service = _LazyProxy(get_embedding_service)
chunking_service  = _LazyProxy(get_chunking_service)
qdrant_service    = _LazyProxy(get_qdrant_service)
