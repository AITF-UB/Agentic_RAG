import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)


class QdrantService:

    def __init__(
        self,
        host,
        port,
        collection_name
    ):
        self.client = QdrantClient(
            host=host,
            port=port
        )

        self.collection_name = collection_name

    def create_collection(
        self,
        vector_size
    ):

        collections = [
            c.name
            for c in self.client.get_collections().collections
        ]

        if self.collection_name in collections:
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        )

    def insert(
        self,
        embedding,
        payload
    ):

        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload=payload
                )
            ]
        )

    def search(self, query_vector, user_id, sesi_id, top_k=5):
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="sesi_id", match=MatchValue(value=sesi_id))
                ]
            )
        )
        return results.points

        return self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id)
                    ),
                    FieldCondition(
                        key="sesi_id",
                        match=MatchValue(value=sesi_id)
                    )
                ]
            )
        )