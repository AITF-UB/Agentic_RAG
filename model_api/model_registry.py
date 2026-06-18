# -*- coding: utf-8 -*-
"""
model_registry.py
=================
Centralized singleton store untuk semua model ML.

Model yang dikelola:
  1. Dense    — SentenceTransformer (BAAI/bge-m3)
  2. Sparse   — SPLADE (naver/splade-cocondenser-ensembledistil)
  3. Reranker — CrossEncoder
  4. Docling  — DocumentConverter (PDF extraction + OCR)

Semua model di-load lazy (saat pertama kali dipanggil) dan disimpan
sebagai singleton — pemanggilan berikutnya langsung mengembalikan
instance yang sudah ada tanpa loading ulang.

Penggunaan:
    from model_registry import get_dense_model, get_sparse_model, get_reranker
    from model_registry import get_docling_converter

    model = get_dense_model()          # SentenceTransformer
    splade = get_sparse_model()        # SpladeEncoder
    reranker = get_reranker()          # CrossEncoder
    converter = get_docling_converter()# DocumentConverter

    # Pre-load semua model saat startup (opsional):
    from model_registry import preload_all
    preload_all()
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np
import torch
from dotenv import load_dotenv
import requests

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

DENSE_MODEL_NAME    = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
SPARSE_MODEL_NAME   = os.getenv("SPARSE_MODEL", "naver/splade-cocondenser-ensembledistil")
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def get_device() -> str:
    """Kembalikan device string ('cuda' atau 'cpu')."""
    return DEVICE


# ══════════════════════════════════════════════════════════════════════════════
# SPLADE ENCODER
# ══════════════════════════════════════════════════════════════════════════════

class SpladeEncoder:
    """
    Encoder SPLADE untuk sparse vector.

    Mendukung:
      - encode_query(text)       → dict {indices, values}  (untuk search di tools.py)
      - encode_passages(texts)   → List[np.ndarray]        (untuk ingest di full_pipeline.py)
      - to_qdrant(vec)           → SparseVector             (untuk ingest ke Qdrant)
    """

    def __init__(self, model_name: str, device: str):
        from transformers import AutoTokenizer, AutoModelForMaskedLM

        print(f"⏳ Loading SPLADE: {model_name} ...")
        self.device    = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model     = AutoModelForMaskedLM.from_pretrained(model_name).to(device)
        self.model.eval()
        print(f"✅ SPLADE loaded ({device})")

    def _encode_batch(self, texts: List[str]) -> np.ndarray:
        enc = self.tokenizer(
            texts, return_tensors="pt", padding=True, truncation=True, max_length=512,
        ).to(self.device)
        with torch.no_grad():
            logits = self.model(**enc).logits
        relu_log = torch.log1p(torch.relu(logits))
        mask     = enc["attention_mask"].unsqueeze(-1).float()
        sparse   = torch.max(relu_log * mask, dim=1).values
        return sparse.cpu().numpy()

    def encode_query(self, text: str) -> dict:
        """Encode satu query → dict {indices, values} untuk search."""
        vec = self._encode_batch([text])[0]
        nonzero_idx = np.nonzero(vec)[0]
        return {
            "indices": nonzero_idx.tolist(),
            "values":  vec[nonzero_idx].tolist(),
        }

    def encode_passages(self, texts: List[str]) -> List[np.ndarray]:
        """Encode batch passages → list of sparse vectors untuk ingest."""
        return list(self._encode_batch(texts))

    @staticmethod
    def to_qdrant(vec: np.ndarray):
        """Konversi numpy sparse vector ke SparseVector Qdrant."""
        from qdrant_client.models import SparseVector

        nonzero_idx = np.nonzero(vec)[0]
        return SparseVector(
            indices=nonzero_idx.tolist(),
            values=vec[nonzero_idx].tolist(),
        )


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON STORE
# ══════════════════════════════════════════════════════════════════════════════

_dense_model      = None
_sparse_model     = None
_reranker_model   = None
_docling_converter = None


class ProxyDenseModel:
    def __init__(self, url):
        self.url = url
    
    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        resp = requests.post(f"{self.url}/embed/dense", json={"texts": texts, "normalize_embeddings": normalize_embeddings}, timeout=120)
        resp.raise_for_status()
        vectors = np.array(resp.json()["vectors"])
        if not convert_to_numpy:
            vectors = torch.tensor(vectors)
        return vectors


class ProxySparseModel:
    def __init__(self, url):
        self.url = url
    
    def encode_query(self, text: str) -> dict:
        resp = requests.post(f"{self.url}/embed/sparse/query", json={"text": text}, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def encode_passages(self, texts: List[str]) -> List[np.ndarray]:
        resp = requests.post(f"{self.url}/embed/sparse/passages", json={"texts": texts}, timeout=120)
        resp.raise_for_status()
        results = resp.json()["vectors"]
        
        # reconstruct sparse vectors to match original SpladeEncoder output
        # SpladeEncoder original `encode_passages` returns list of sparse numpy arrays of shape (vocab_size,)
        # Wait, the proxy API returns {"indices": [...], "values": [...]}
        # But `tools.py` just calls `.encode_passages()`
        # Wait, `full_pipeline.py` calls `.encode_passages()` and then stores them.
        # It's better to reconstruct a fake large numpy array? No, wait!
        # The original `encode_passages` returned `List[np.ndarray]` where the array shape was (30522,) which is huge.
        # But wait, Qdrant payload generation in `full_pipeline.py` takes it and does:
        # `SparseVector(indices=nonzero_idx.tolist(), values=vec[nonzero_idx].tolist())`
        # Actually, let's just reconstruct the full array to perfectly match original behavior
        # Assuming vocab size is 30522 (bert)
        vocab_size = 30522 
        recon = []
        for r in results:
            arr = np.zeros(vocab_size, dtype=np.float32)
            arr[r["indices"]] = r["values"]
            recon.append(arr)
        return recon


class ProxyReranker:
    def __init__(self, url):
        self.url = url
    
    def predict(self, pairs, **kwargs):
        query = pairs[0][0]
        texts = [p[1] for p in pairs]
        resp = requests.post(f"{self.url}/rerank", json={"query": query, "texts": texts}, timeout=120)
        resp.raise_for_status()
        return resp.json()["scores"]


def get_dense_model():
    """
    Kembalikan singleton SentenceTransformer atau API Proxy.
    """
    api_url = os.getenv("MODEL_API_URL")
    if api_url:
        return ProxyDenseModel(api_url)

    global _dense_model
    if _dense_model is None:
        from sentence_transformers import SentenceTransformer

        print(f"⏳ Loading dense model: {DENSE_MODEL_NAME} ...")
        _dense_model = SentenceTransformer(DENSE_MODEL_NAME)
        print(f"✅ Dense model loaded.")
    return _dense_model


def get_sparse_model():
    """
    Kembalikan singleton SpladeEncoder atau API Proxy.
    """
    api_url = os.getenv("MODEL_API_URL")
    if api_url:
        return ProxySparseModel(api_url)

    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SpladeEncoder(SPARSE_MODEL_NAME, DEVICE)
    return _sparse_model


def get_reranker():
    """
    Kembalikan singleton CrossEncoder atau API Proxy.
    """
    api_url = os.getenv("MODEL_API_URL")
    if api_url:
        return ProxyReranker(api_url)

    global _reranker_model
    if _reranker_model is None:
        from sentence_transformers import CrossEncoder

        print(f"⏳ Loading reranker: {RERANKER_MODEL_NAME} ...")
        _reranker_model = CrossEncoder(RERANKER_MODEL_NAME, device=DEVICE)
        print(f"✅ Reranker loaded ({DEVICE}).")
    return _reranker_model

def get_docling_converter():
    """
    Kembalikan singleton Docling DocumentConverter.
    """
    # NOTE: Proxy for docling is handled directly in full_pipeline.py
    global _docling_converter
    if _docling_converter is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat

        print("⏳ Loading Docling DocumentConverter (+ OCR models) ...")
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_page_images   = True
        pipeline_options.generate_table_images   = True
        pipeline_options.generate_picture_images = True
        pipeline_options.do_ocr = True
        pipeline_options.images_scale = 3.0

        _docling_converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        print("✅ Docling DocumentConverter loaded.")
    return _docling_converter


# ══════════════════════════════════════════════════════════════════════════════
# PRELOAD
# ══════════════════════════════════════════════════════════════════════════════

def preload_all() -> None:
    """
    Pre-load semua model ke memory.

    Panggil di lifespan startup agar request pertama tidak lambat.
    """
    api_url = os.getenv("MODEL_API_URL")
    if api_url:
        print(f"🌐 Running in proxy mode. Models are served by {api_url}. Skipping local preload.")
        return

    print("=" * 60)
    print("  MODEL REGISTRY — Pre-loading all models")
    print("=" * 60)
    print(f"  Device  : {DEVICE}")
    print(f"  Dense   : {DENSE_MODEL_NAME}")
    print(f"  Sparse  : {SPARSE_MODEL_NAME}")
    print(f"  Reranker: {RERANKER_MODEL_NAME}")
    print(f"  Docling : DocumentConverter (OCR)")
    print("=" * 60)

    get_dense_model()
    get_sparse_model()
    get_reranker()
    get_docling_converter()

    print("=" * 60)
    print("  ✅ All models loaded and ready.")
    print("=" * 60)
