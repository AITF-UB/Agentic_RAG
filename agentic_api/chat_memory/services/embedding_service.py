class EmbeddingService:

    def __init__(self, model_name: str):
        # Import here to avoid pulling heavy native libs at module import time
        # which can crash the Python process on some Windows setups.
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            model_name,
            trust_remote_code=True
        )

    def embed(self, text: str):
        return self.model.encode(
            text,
            normalize_embeddings=True
        ).tolist()