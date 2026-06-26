import sys
from pathlib import Path

# Memastikan agentic_api ada di sys.path agar bisa import model_registry
_THIS_DIR = Path(__file__).resolve().parent.parent.parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

class EmbeddingService:

    def __init__(self, model_name: str):
        # Menggunakan proxy model dari model_registry agar tidak load model berat lokal
        from model_registry import get_dense_model
        self.model = get_dense_model()

    def embed(self, text: str):
        # ProxyDenseModel.encode mereturn numpy array 2D. Ambil elemen pertama lalu tolist.
        vectors = self.model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        return vectors[0].tolist()