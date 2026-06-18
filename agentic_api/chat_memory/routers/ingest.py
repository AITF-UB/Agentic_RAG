from fastapi import APIRouter

from chat_memory.schemas import IngestChatRequest

from chat_memory.dependencies import (
    embedding_service,
    qdrant_service,
    chunking_service
)

router = APIRouter(
    prefix="/chat-memory",
    tags=["Chat Memory Ingest"]
)

CHUNK_SIZE = 1800


@router.post("/ingest")
def ingest_chat(request: IngestChatRequest):

    page_content = f"""
User:
{request.user_message}

Assistant:
{request.assistant_message}
""".strip()

    # 1 chat_id = 1 pasangan Q&A
    # Chunking hanya jika terlalu panjang

    if len(page_content) <= CHUNK_SIZE:
        chunks = [page_content]
    else:
        chunks = chunking_service.split_text(
            page_content
        )

    for idx, chunk in enumerate(chunks):

        embedding = embedding_service.embed(
            chunk
        )

        payload = {
            "user_id": request.user_id,
            "sesi_id": request.sesi_id,
            "chat_id": request.chat_id,

            "chunk_index": idx,
            "total_chunks": len(chunks),

            "publish_id": request.publish_id,
            "level": request.level,
            "emosi": request.emosi,

            "page_content": chunk
        }

        qdrant_service.insert(
            embedding=embedding,
            payload=payload
        )

    return {
        "status": "success",
        "user_id": request.user_id,
        "sesi_id": request.sesi_id,
        "chat_id": request.chat_id,
        "total_chunks": len(chunks)
    }