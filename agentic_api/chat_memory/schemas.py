from pydantic import BaseModel
from typing import Optional


class IngestChatRequest(BaseModel):
    user_id: str

    sesi_id: str

    chat_id: str

    publish_id: Optional[str] = None

    level: Optional[str] = None

    emosi: Optional[str] = None

    user_message: str

    assistant_message: str


class RetrieveChatRequest(BaseModel):
    query: str

    user_id: str

    sesi_id: str

    top_k: int = 5