import os

from pydantic import BaseModel


class Settings(BaseModel):
    collection_name: str = "chat_memory"
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", 6333))
    embedding_model: str = "BAAI/bge-m3"
    chunk_size: int = 1800
    chunk_overlap: int = 200

settings = Settings()