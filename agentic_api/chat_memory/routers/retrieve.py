from chat_memory.schemas import RetrieveChatRequest

from chat_memory.dependencies import (
    embedding_service,
    qdrant_service
)

router = APIRouter(
    prefix="/chat-memory",
    tags=["Chat Memory Retriever"]
)


@router.post("/retrieve")
def retrieve_chat_memory(
    request: RetrieveChatRequest
):

    query_embedding = embedding_service.embed(
        request.query
    )

    results = qdrant_service.search(
        query_vector=query_embedding,
        user_id=request.user_id,
        sesi_id=request.sesi_id,
        top_k=request.top_k
    )

    formatted_results = []

    for result in results:

        formatted_results.append(
            {
                "score": result.score,
                "page_content": result.payload.get(
                    "page_content"
                ),
                "metadata": {
                    k: v
                    for k, v in result.payload.items()
                    if k != "page_content"
                }
            }
        )

    return {
        "query": request.query,
        "user_id": request.user_id,
        "sesi_id": request.sesi_id,
        "top_k": request.top_k,
        "total_results": len(
            formatted_results
        ),
        "results": formatted_results
    }