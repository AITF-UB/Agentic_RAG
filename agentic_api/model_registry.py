# -*- coding: utf-8 -*-
"""
model_registry.py (Proxy Client Version)
=================
Versi ini hanya berisi proxy class untuk memanggil `model_api` via HTTP.
Tidak ada model Machine Learning berat yang diload di sini.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# Global HTTP Session dengan Connection Pooling (HTTP Keep-Alive)
_http_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=30)
_http_session.mount("http://", _adapter)
_http_session.mount("https://", _adapter)


class ProxyDenseModel:
    def __init__(self, url):
        self.url = url
    
    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        resp = _http_session.post(f"{self.url}/embed/dense", json={"texts": texts, "normalize_embeddings": normalize_embeddings}, timeout=120)
        resp.raise_for_status()
        vectors = np.array(resp.json()["vectors"])
        if not convert_to_numpy:
            import torch
            vectors = torch.tensor(vectors)
        return vectors


class ProxySparseModel:
    def __init__(self, url):
        self.url = url
    
    def encode_query(self, text: str) -> dict:
        resp = _http_session.post(f"{self.url}/embed/sparse/query", json={"text": text}, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def encode_passages(self, texts: List[str]) -> List[np.ndarray]:
        resp = _http_session.post(f"{self.url}/embed/sparse/passages", json={"texts": texts}, timeout=120)
        resp.raise_for_status()
        results = resp.json()["vectors"]
        
        vocab_size = 30522 
        recon = []
        for r in results:
            arr = np.zeros(vocab_size, dtype=np.float32)
            arr[r["indices"]] = r["values"]
            recon.append(arr)
        return recon

    @staticmethod
    def to_qdrant(vec: np.ndarray):
        from qdrant_client.models import SparseVector
        nonzero_idx = np.nonzero(vec)[0]
        return SparseVector(
            indices=nonzero_idx.tolist(),
            values=vec[nonzero_idx].tolist(),
        )


class ProxyReranker:
    def __init__(self, url):
        self.url = url
    
    def predict(self, pairs, **kwargs):
        query = pairs[0][0]
        texts = [p[1] for p in pairs]
        resp = _http_session.post(f"{self.url}/rerank", json={"query": query, "texts": texts}, timeout=120)
        resp.raise_for_status()
        return resp.json()["scores"]


def _get_api_url():
    url = os.getenv("MODEL_API_URL")
    if not url:
        raise RuntimeError("MODEL_API_URL tidak diset. agentic_api membutuhkan model_api untuk berjalan.")
    return url

def get_dense_model():
    return ProxyDenseModel(_get_api_url())

def get_sparse_model():
    return ProxySparseModel(_get_api_url())

def get_reranker():
    return ProxyReranker(_get_api_url())

def get_docling_converter():
    """
    Pada versi proxy, Docling langsung di-handle di full_pipeline.py dengan merequest ke API.
    Fungsi ini dibiarkan untuk kompatibilitas jika ada yang memanggil, tapi harusnya tidak dipakai lokal.
    """
    raise NotImplementedError("Gunakan API /extract/docling secara langsung. Docling lokal tidak tersedia di microservice ini.")

def preload_all() -> None:
    api_url = os.getenv("MODEL_API_URL")
    if api_url:
        print(f"🌐 Running in proxy mode. Models are served by {api_url}.")
    else:
        print("⚠️ MODEL_API_URL belum diset!")
