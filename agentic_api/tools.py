import os
import json
import re
import uuid
import time
import pickle
import torch
import numpy as np
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any
import asyncio

from dotenv import load_dotenv
load_dotenv()

from rank_bm25 import BM25Okapi

# ── Import model dari centralized registry ──────────────────────────────────
from model_registry import (
    get_dense_model,
    get_sparse_model,
    get_reranker,
)

# Alias agar kode lama yang import get_sentence_model tetap kompatibel
get_sentence_model = get_dense_model

# ================================================================
# Models Configuration
# ================================================================
from qdrant_client import QdrantClient
from qdrant_client.http import models

QDRANT_HOST_RAW    = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT        = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY     = os.getenv("QDRANT_API_KEY", "")

if QDRANT_HOST_RAW and (QDRANT_HOST_RAW.startswith("http://") or QDRANT_HOST_RAW.startswith("https://")):
    qdrant_client = QdrantClient(url=f"{QDRANT_HOST_RAW}:{QDRANT_PORT}", api_key=QDRANT_API_KEY if QDRANT_API_KEY else None, timeout=120, check_compatibility=False)
else:
    qdrant_client = QdrantClient(host=QDRANT_HOST_RAW, port=QDRANT_PORT, api_key=QDRANT_API_KEY if QDRANT_API_KEY else None, https=False, timeout=120, check_compatibility=False)

TEXT_COLLECTION    = os.getenv("QDRANT_TEXT_COLLECTION")

EXTRACTION_BASE_DIR = Path(__file__).resolve().parent / "extraction"

BM25_CACHE_PATH = Path(__file__).resolve().parent / f"bm25_{TEXT_COLLECTION}.pkl"

# ================================================================
# Search Mode Configuration
# ─────────────────────────────────────────────────────────────────
# SEARCH_MODE mengontrol strategi retrieval yang digunakan:
#
#   "dense"   → Hanya dense vector search (aktif untuk production saat ini)
#               Lebih cepat, resource lebih ringan, cocok saat load tinggi.
#
#   "hybrid"  → Dense + SPLADE + BM25 + RRF fusion + rerank
#               Akurasi lebih tinggi, tapi lebih berat & lambat.
#               Aktifkan kembali ketika infrastruktur sudah siap.
#
# Untuk switch mode, cukup ubah nilai env SEARCH_MODE di .env:
#   SEARCH_MODE=dense    ← production sekarang
#   SEARCH_MODE=hybrid   ← aktifkan saat siap
# ================================================================
SEARCH_MODE: str = os.getenv("SEARCH_MODE", "dense").lower()
assert SEARCH_MODE in ("dense", "hybrid"), (
    f"SEARCH_MODE harus 'dense' atau 'hybrid', dapat: '{SEARCH_MODE}'"
)

print(f"🔍 Search mode aktif: [{SEARCH_MODE.upper()}]")

# ================================================================
# Query Embedding Cache — menghindari encode ulang query sama
# ================================================================
_query_embed_cache: Dict[str, tuple] = {}  # query -> (vector, timestamp)
_QUERY_EMBED_TTL = 300  # Lokasi file local untuk cache BM25
BM25_CACHE_FILE = os.path.join(os.path.dirname(__file__), "bm25_hybrid_new.pkl")
# Versi struktur objek index BM25
BM25_CACHE_VERSION = "v2"

# Lazy load globals (BM25 only — model singletons sekarang di model_registry)
_bm25 = None
_bm25_docs = []
_chunk_expansion_cache = {}

# ================================================================
# Tokenizer (for BM25)
# ================================================================
def tokenize(text: str):
    text = text.lower()
    return re.findall(r"\w+", text)

async def embed_text_for_text_vdb(query: str) -> list:
    """Embed query dengan cache — menghindari encode ulang query yang sama."""
    cache_key = query.strip()
    now = time.time()
    
    # Cek cache
    if cache_key in _query_embed_cache:
        cached_vector, cached_ts = _query_embed_cache[cache_key]
        if now - cached_ts < _QUERY_EMBED_TTL:
            return cached_vector
    
    model = get_sentence_model()
    prefixed = f"query: {cache_key}"
    loop = asyncio.get_event_loop()
    vector = await loop.run_in_executor(None, lambda: model.encode([prefixed], normalize_embeddings=True, convert_to_numpy=True)[0])
    vector_list = vector.tolist()
    
    # Simpan ke cache
    _query_embed_cache[cache_key] = (vector_list, now)
    return vector_list

# ================================================================
# 2. Qdrant Search Engine
# ================================================================
async def _search_qdrant_dense(collection: str, vector: list, top_k: int, filter_payload = None) -> list:
    def _do():
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                result = qdrant_client.query_points(
                    collection_name=collection,
                    query=vector,
                    using="dense",
                    limit=top_k,
                    query_filter=filter_payload,
                    with_payload=models.PayloadSelectorExclude(exclude=["has_visual_content"])
                )
                hits = result.points
                results = []
                for hit in hits:
                    payload_data = hit.payload or {}
                    results.append({
                        "id": hit.id,
                        "score": hit.score,
                        "text": payload_data.get("text", payload_data.get("page_content", "N/A")),
                        "metadata": payload_data,
                        "source_file": payload_data.get("source_file", "N/A"),
                        "retrieval_type": "dense"
                    })
                return results
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠️ Qdrant dense connection error (attempt {attempt + 1}/{max_retries + 1}): {e}, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                print(f"❌ Error query Qdrant Dense (after {max_retries + 1} attempts): {e}")
                return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)

# ── Hybrid-only components (tidak dipakai saat SEARCH_MODE=dense) ──────────

async def _search_qdrant_splade(collection: str, query: str, top_k: int, filter_payload = None) -> list:
    def _do():
        model = get_sparse_model()
        sparse_vector = model.encode_query(query)
        
        if isinstance(sparse_vector, dict):
            q_sparse = models.SparseVector(
                indices=sparse_vector["indices"],
                values=sparse_vector["values"]
            )
        else:
            q_sparse = sparse_vector

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                result = qdrant_client.query_points(
                    collection_name=collection,
                    query=q_sparse,
                    using="sparse",
                    limit=top_k,
                    query_filter=filter_payload,
                    with_payload=models.PayloadSelectorExclude(exclude=["has_visual_content"])
                )
                hits = result.points

                results = []
                for hit in hits:
                    payload_data = hit.payload or {}
                    results.append({
                        "id": hit.id,
                        "score": hit.score,
                        "text": payload_data.get("text", payload_data.get("page_content", "N/A")),
                        "metadata": payload_data,
                        "source_file": payload_data.get("source_file", "N/A"),
                        "retrieval_type": "splade"
                    })
                return results
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠️ Qdrant splade connection error (attempt {attempt + 1}/{max_retries + 1}): {e}, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                print(f"❌ Qdrant splade connection error (after {max_retries + 1} attempts): {e}")
                return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)

async def _fetch_qdrant_points_by_ids(point_ids: list, collection: str) -> list:
    """Fetch full points (with ALL payloads) by their IDs.
    Returns list of {id, score, payload} dicts.
    Uses POST /collections/{collection}/points for batch fetching.
    """
    def _do():
        if not point_ids: return []
        for attempt in range(3):
            try:
                records = qdrant_client.retrieve(
                    collection_name=collection,
                    ids=point_ids,
                    with_payload=True,
                    with_vectors=False
                )
                return [{"id": r.id, "payload": r.payload} for r in records]
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                print(f"⚠️ Failed to batch fetch points after 3 attempts: {e}")
        return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)

async def _inject_visual_content_batch(collection: str, docs: list) -> list:
    """Menerima list dokumen yang sudah direrank, mengambil visual context dari Qdrant, dan menyisipkannya.
    docs adalah list of dict format standar kita, yang memiliki key 'id' dan 'metadata'.
    """
    ids_to_fetch = [doc.get("id") for doc in docs if doc.get("id") is not None]
    if not ids_to_fetch: return docs
    
    full_points = await _fetch_qdrant_points_by_ids(ids_to_fetch, collection)
    image_lookup = {p.get("id"): p.get("payload", {}).get("has_visual_content", []) for p in full_points if p.get("id") is not None}
    
    for doc in docs:
        doc_id = doc.get("id")
        if doc_id is not None:
            doc.setdefault("metadata", {})["has_visual_content"] = image_lookup.get(doc_id, [])
    return docs

async def _scroll_qdrant(collection: str, scroll_filter, limit: int = 200, max_retries: int = 2) -> list:
    def _do():
        for attempt in range(max_retries + 1):
            try:
                records, _ = qdrant_client.scroll(
                    collection_name=collection,
                    scroll_filter=scroll_filter,
                    limit=limit,
                    with_payload=models.PayloadSelectorExclude(exclude=["has_visual_content"])
                )
                return [{"id": r.id, "payload": r.payload} for r in records]
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠️ Qdrant scroll error (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                print(f"❌ Qdrant scroll error (after {max_retries + 1} attempts): {e}")
                return []
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do)

def _normalize_source_file(raw: str) -> str:
    """Normalisasi source_file: hapus ekstensi, path prefix, suffix pipeline & lowercase.

    Menghasilkan nilai yang konsisten dari input apa pun:
      - "Biologi_Kelas_X.pdf"                    → "biologi_kelas_x"
      - "Biologi_Kelas_X_FINAL_PAGINATED"        → "biologi_kelas_x"
      - "Biologi_Kelas_X_FINAL_PAGINATED_chunks" → "biologi_kelas_x"
      - "biologi_kelas_x"                        → "biologi_kelas_x"
    """
    name = raw.strip().replace("\\", "/")
    name = Path(name).stem  # hapus ekstensi file jika ada
    # Hapus suffix yang ditambahkan oleh pipeline (urutan penting: dari paling spesifik)
    for suffix in ("_chunks", "_FINAL_PAGINATED", "_final_paginated", "_structure"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.lower()


def _build_qdrant_filter(asset_type: Optional[str] = None, source: Optional[str] = None, mata_pelajaran: Optional[str] = None, kelas: Optional[int] = None, source_file: Optional[str] = None, buku_id: Optional[str] = None):
    conditions = []
    if asset_type: conditions.append(models.FieldCondition(key="asset_type", match=models.MatchValue(value=asset_type)))
    if source: conditions.append(models.FieldCondition(key="source", match=models.MatchValue(value=source)))
    if mata_pelajaran: conditions.append(models.FieldCondition(key="mata_pelajaran", match=models.MatchValue(value=mata_pelajaran)))
    if kelas is not None: conditions.append(models.FieldCondition(key="kelas", match=models.MatchValue(value=kelas)))
    if source_file: conditions.append(models.FieldCondition(key="source_file", match=models.MatchValue(value=_normalize_source_file(source_file))))
    if buku_id: conditions.append(models.FieldCondition(key="buku_id", match=models.MatchValue(value=buku_id)))
    return models.Filter(must=conditions) if conditions else None

# ================================================================
# 3. BM25 Sparse Search  (hybrid only)
# ================================================================
def build_bm25_index():
    global _bm25, _bm25_docs
    if _bm25 is not None:
        return
    
    # Cek cache dengan versioning — invalidate jika struktur payload berubah
    cache_valid = False
    if BM25_CACHE_PATH.exists():
        try:
            with open(BM25_CACHE_PATH, "rb") as f:
                cache = pickle.load(f)
            if cache.get("version") == BM25_CACHE_VERSION:
                _bm25 = cache["bm25"]
                _bm25_docs = cache["docs"]
                cache_valid = True
                print(f"📦 Loading BM25 dari cache (version {BM25_CACHE_VERSION}): {BM25_CACHE_PATH}")
                return  # Cache valid, tidak perlu rebuild
            else:
                print(f"⚠️ BM25 cache version mismatch (cache={cache.get('version')}, expected={BM25_CACHE_VERSION}). Building new index...")
        except Exception as e:
            print(f"⚠️ BM25 cache load error: {e}. Building new index...")
    
    print("⏳ Building BM25 index dari Qdrant (pertama kali)...")
    all_points = []
    offset = None
    while True:
        try:
            records, offset = qdrant_client.scroll(
                collection_name=TEXT_COLLECTION,
                limit=1000,
                with_payload=models.PayloadSelectorExclude(exclude=["has_visual_content"]),
                offset=offset
            )
            points = [{"id": r.id, "payload": r.payload} for r in records]
            all_points.extend(points)
            if offset is None: break
        except Exception as e:
            print(f"❌ BM25 scroll error: {e}")
            break
    corpus = []
    docs = []
    for p in all_points:
        payload = p.get("payload", {})
        text = payload.get("text", payload.get("page_content", ""))
        if not text: continue
        # Payload Qdrant FLAT — seluruh payload diperlakukan sebagai metadata
        # (mata_pelajaran, kelas, chunk_index, source_file, dll semua di sini).
        # has_visual_content sudah di-exclude di level request di atas.
        metadata = payload
        docs.append({
            "id": p.get("id"),
            "text": text,
            "metadata": metadata,
            "source_file": payload.get("source_file", "N/A")
        })
        corpus.append(tokenize(text))
    if corpus:
        _bm25 = BM25Okapi(corpus)
        _bm25_docs = docs
        with open(BM25_CACHE_PATH, "wb") as f:
            pickle.dump({"version": BM25_CACHE_VERSION, "bm25": _bm25, "docs": _bm25_docs}, f)
        print(f"✅ BM25 index built & cached (v{BM25_CACHE_VERSION}): {len(docs)} docs")
    else:
        print("⚠ Tidak ada dokumen untuk BM25.")

async def sparse_search(query: str, top_k: int = 10, mata_pelajaran: Optional[str] = None, kelas: Optional[int] = None, source_file: Optional[str] = None):
    tokenized_query = tokenize(query)
    
    def _prepare():
        build_bm25_index()
        if _bm25 is None: return None
        return _bm25.get_scores(tokenized_query)

    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(None, _prepare)
    
    if scores is None: return []

    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    norm_source = _normalize_source_file(source_file) if source_file else None

    results = []
    for idx in ranked_idx:
        doc = dict(_bm25_docs[idx])
        # Soft-filter matching untuk mapel, kelas & source_file karena BM25 ditarik full corpus
        meta = doc.get("metadata", {})
        if mata_pelajaran and meta.get("mata_pelajaran") != mata_pelajaran:
            continue
        if kelas is not None and meta.get("kelas") != kelas:
            continue
        if norm_source and meta.get("source_file", "").lower() != norm_source:
            continue

        doc["bm25_score"] = float(scores[idx])
        doc["retrieval_type"] = "sparse"
        results.append(doc)
        if len(results) >= top_k:
            break

    return results

# ================================================================
# 4. RRF, Dedup, Expand, Rerank  (hybrid only, kecuali expand)
# ================================================================
def reciprocal_rank_fusion(dense_results, splade_results, bm25_results, k=60):
    fused_scores = {}

    def add_to_fusion(results, type_key):
        for rank, doc in enumerate(results):
            text = doc["text"]
            rrf_score = 1 / (k + rank + 1)
            if text not in fused_scores:
                fused_scores[text] = {"doc": dict(doc), "score": 0, "dense_score": 0, "splade_score": 0, "bm25_score": 0}
            fused_scores[text]["score"] += rrf_score
            if type_key == "dense":
                fused_scores[text]["dense_score"] = doc.get("score", 0)
            elif type_key == "splade":
                fused_scores[text]["splade_score"] = doc.get("score", 0)
            elif type_key == "bm25":
                fused_scores[text]["bm25_score"] = doc.get("bm25_score", 0)

    add_to_fusion(dense_results, "dense")
    add_to_fusion(splade_results, "splade")
    add_to_fusion(bm25_results, "bm25")

    reranked = sorted(fused_scores.values(), key=lambda x: x["score"], reverse=True)
    final_results = []
    for item in reranked:
        doc = item["doc"]
        doc["rrf_score"] = item["score"]
        doc["dense_score"] = item["dense_score"]
        doc["splade_score"] = item["splade_score"]
        doc["bm25_score"] = item["bm25_score"]
        final_results.append(doc)
    return final_results

def deduplicate(docs: list) -> list:
    unique = []
    seen = set()
    for doc in docs:
        metadata = doc.get("metadata", {})
        chunk_index = metadata.get("chunk_index")
        source_file = doc.get("source_file", "")
        uid = (source_file, chunk_index) if chunk_index is not None else doc["text"]
        if uid in seen: continue
        seen.add(uid)
        unique.append(doc)
    return unique

async def _fetch_chunks_for_source(source_file: str, min_idx: int, max_idx: int) -> list:
    """Ambil chunk per source_file dengan limit scroll untuk efisiensi."""
    points = await _scroll_qdrant(TEXT_COLLECTION, scroll_filter={"must": [{"key": "source_file", "match": {"value": source_file}}]}, limit=50)
    chunks = []
    for p in points:
        payload = p.get("payload", {})
        # Payload flat — chunk_index langsung di top-level payload
        idx = payload.get("chunk_index")
        if idx is not None and min_idx <= idx <= max_idx:
            text = payload.get("text", payload.get("page_content", ""))
            if text: chunks.append((idx, text))
    chunks.sort(key=lambda x: x[0])
    return chunks

async def expand_chunk_context(docs: list, window=1) -> list:
    """Expand chunk context dengan batch scroll per source_file — mengurangi N+1 query Qdrant."""
    expanded_docs = []
    
    # Group dokumen yang butuh chunk expansion per source_file
    needs_expansion = []
    no_chunk_docs = []
    
    for doc in docs:
        metadata = doc.get("metadata", {})
        chunk_index = metadata.get("chunk_index")
        source_file = doc.get("source_file")
        
        if chunk_index is None:
            doc["expanded_text"] = doc["text"]
            no_chunk_docs.append(doc)
            continue
        
        cache_key = (source_file, chunk_index, window)
        if cache_key in _chunk_expansion_cache:
            doc["expanded_text"] = _chunk_expansion_cache[cache_key]
            no_chunk_docs.append(doc)
            continue
        
        needs_expansion.append((doc, source_file, chunk_index, cache_key))
    
    # Group by source_file — scroll sekali per source, bukan N kali
    source_groups: Dict[str, list] = {}
    for doc, source_file, chunk_index, cache_key in needs_expansion:
        if source_file not in source_groups:
            source_groups[source_file] = []
        source_groups[source_file].append((doc, chunk_index, cache_key))
    
    # Batch scroll per source_file
    for source_file, group_items in source_groups.items():
        all_chunk_indices = {idx for _, idx, _ in group_items}
        min_idx = min(all_chunk_indices) - window
        max_idx = max(all_chunk_indices) + window
        
        # Scroll sekali untuk semua chunk yang dibutuhkan source ini
        chunks = await _fetch_chunks_for_source(source_file, min_idx, max_idx)
        chunk_map = {idx: text for idx, text in chunks}
        
        # Assign expanded text ke setiap dokumen di group ini
        for doc, chunk_index, cache_key in group_items:
            # Kumpulkan chunk di window
            window_chunks = []
            for offset in range(-window, window + 1):
                target_idx = chunk_index + offset
                if target_idx in chunk_map:
                    window_chunks.append((target_idx, chunk_map[target_idx]))
            
            window_chunks.sort(key=lambda x: x[0])
            expanded_text = "\n".join(text for _, text in window_chunks) if window_chunks else doc["text"]
            _chunk_expansion_cache[cache_key] = expanded_text
            doc["expanded_text"] = expanded_text
            expanded_docs.append(doc)
    
    # Gabungkan dokumen yang tidak perlu expand
    expanded_docs.extend(no_chunk_docs)
    return expanded_docs

async def rerank_results(query: str, docs: list, top_k: int = 5) -> list:
    if not docs: return []
    reranker = get_reranker()
    pairs = [(query, doc.get("expanded_text", doc["text"])) for doc in docs]
    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(None, lambda: reranker.predict(pairs, batch_size=16, show_progress_bar=False))
    ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)

    reranked_docs = []
    for score, doc in ranked[:top_k]:
        doc["rerank_score"] = float(score)
        reranked_docs.append(doc)
    return reranked_docs


# ================================================================
# 5. Pipeline Search Utama
# ================================================================
async def _retrieve_dense(query: str, top_k: int, mata_pelajaran: Optional[str], kelas: Optional[int], source_file: Optional[str] = None, buku_id: Optional[str] = None) -> list:
    """
    Dense-only retrieval: embed → Qdrant dense search → dedup.
    Tidak menjalankan SPLADE, BM25, RRF, maupun reranker sehingga
    lebih ringan dan cepat untuk production.
    """
    retrieve_k = max(top_k * 3, 20)

    vector = await embed_text_for_text_vdb(query)
    payload_filter = _build_qdrant_filter(mata_pelajaran=mata_pelajaran, kelas=kelas, source_file=source_file, buku_id=buku_id)
    hits = await _search_qdrant_dense(TEXT_COLLECTION, vector, retrieve_k, filter_payload=payload_filter)

    results = []
    for hit in hits:
        # Payload Qdrant FLAT (tidak ada nesting "metadata").
        # Seluruh payload (chunk_index, mata_pelajaran, kelas,
        # has_visual_content, dll) diperlakukan sebagai metadata,
        # supaya dedup, chunk expansion, dan info gambar di
        # RAGEngine.unified_search bisa berfungsi dengan benar.
        payload = hit.get("payload", {})
        results.append({
            "id": hit.get("id"),
            "score": hit.get("score", 0.0),
            "text": payload.get("text", payload.get("page_content", "N/A")),
            "metadata": payload,
            "source_file": payload.get("source_file", "N/A"),
            "retrieval_type": "dense",
        })

    unique_results = deduplicate(results)
    # Kembalikan top_k teratas (sudah diurutkan Qdrant by score)
    top_results = unique_results[:top_k]
    return await _inject_visual_content_batch(TEXT_COLLECTION, top_results)


async def _retrieve_hybrid(query: str, top_k: int, mata_pelajaran: Optional[str], kelas: Optional[int], source_file: Optional[str] = None, buku_id: Optional[str] = None) -> list:
    """
    Hybrid retrieval: Dense + SPLADE + BM25 → RRF fusion → dedup
    → chunk expansion → rerank.
    Lebih akurat namun lebih berat — gunakan saat infrastruktur siap.
    """
    retrieve_k = max(top_k * 5, 15)

    # 1. Dense Search
    vector = await embed_text_for_text_vdb(query)
    payload_filter = _build_qdrant_filter(mata_pelajaran=mata_pelajaran, kelas=kelas, source_file=source_file, buku_id=buku_id)
    hits = await _search_qdrant_dense(TEXT_COLLECTION, vector, retrieve_k, filter_payload=payload_filter)
    dense_results = []
    for hit in hits:
        # Payload Qdrant FLAT — seluruh payload diperlakukan sebagai metadata.
        payload = hit.get("payload", {})
        dense_results.append({
            "id": hit.get("id"),
            "score": hit.get("score", 0.0),
            "text": payload.get("text", payload.get("page_content", "N/A")),
            "metadata": payload,
            "source_file": payload.get("source_file", "N/A"),
            "retrieval_type": "dense"
        })

    # 2. Sparse Search (SPLADE & BM25)
    splade_results = await _search_qdrant_splade(TEXT_COLLECTION, query, top_k=retrieve_k, filter_payload=payload_filter)
    bm25_results = await sparse_search(query, top_k=retrieve_k, mata_pelajaran=mata_pelajaran, kelas=kelas, source_file=source_file)

    # 3. RRF + Dedup + Expand
    fused_results = reciprocal_rank_fusion(dense_results, splade_results, bm25_results)
    unique_results = deduplicate(fused_results)
    
    # [OPTIMASI RERANKER & EXPANSION]
    # Batasi dokumen yang masuk ke proses ekspansi dan reranking (max 15).
    # Ini sangat penting agar Qdrant tidak di-query 90x untuk ekspansi,
    # dan model reranker (cross-encoder) tidak kewalahan memproses teks.
    docs_to_process = unique_results[:15]
    
    expanded_results = await expand_chunk_context(docs_to_process, window=1)

    # 4. Rerank
    reranked_results = await rerank_results(query, expanded_results, top_k=top_k)
    return await _inject_visual_content_batch(TEXT_COLLECTION, reranked_results)


async def retrieve_text(query: str, top_k: int = 5, mata_pelajaran: Optional[str] = None, kelas: Optional[int] = None, source_file: Optional[str] = None, buku_id: Optional[str] = None) -> list:
    """
    Entry point retrieval. Memilih strategi berdasarkan SEARCH_MODE:
      - "dense"  → _retrieve_dense()   (default production)
      - "hybrid" → _retrieve_hybrid()  (aktifkan saat siap)
    """
    if not query.strip():
        return []

    if SEARCH_MODE == "hybrid":
        return await _retrieve_hybrid(query, top_k, mata_pelajaran, kelas, source_file, buku_id)
    else:
        return await _retrieve_dense(query, top_k, mata_pelajaran, kelas, source_file, buku_id)

def extract_source(chunks: List[dict]) -> List[str]:
    sources = set()
    for c in chunks:
        src = c.get("source_file")
        if src and src != "N/A":
            # Hapus ekstensi file
            src = re.sub(r'\.[a-zA-Z0-9]+$', '', src)
            # Hapus suffix yang tidak perlu
            src = re.sub(r'(?i)[_ -]*(final|paginated|chunks|rev|press|bab).*$', '', src)
            # Bersihkan dan ubah underscore jadi spasi
            src = src.replace("_", " ").strip(' -')
            if src:
                sources.add(src)
    return list(sources)

# ================================================================
# 6. Dynamic RAG Engine
# ================================================================
class RAGEngine:
    @staticmethod
    def get_k_for_type(tipe: str) -> int:
        if tipe == "bacaan": return 8
        if tipe == "flashcard": return 6
        if tipe == "mindmap": return 8
        return 8

    @staticmethod
    async def unified_search(query: str, tipe: str, mapel: Optional[str] = None, kelas: Optional[int] = None, source_file: Optional[str] = None, buku_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform full pipeline search with dynamic chunk sizing and multimodal metadata capabilities.

        Ketika `buku_id` diberikan, melakukan dua pencarian:
          1. Search normal tanpa filter buku_id → ambil chunk dari file RAG bawaan
          2. Search spesifik dengan filter buku_id → ambil chunk dari buku tertentu
        Hasilnya digabung & di-dedup, dengan chunk spesifik buku diutamakan.
        """
        k_text = RAGEngine.get_k_for_type(tipe)

        if buku_id:
            texts = await RAGEngine._search_with_book_reference(query, k_text, mapel, kelas, buku_id)
        else:
            texts = await retrieve_text(query, top_k=k_text, mata_pelajaran=mapel, kelas=kelas, source_file=source_file)

        images = []
        if tipe in ["quiz_pg", "quiz_essay", "bacaan"]:
            for t in texts:
                # metadata sekarang = seluruh payload (flat), jadi
                # has_visual_content benar-benar terbaca dari Qdrant.
                vis = t.get("metadata", {}).get("has_visual_content", [])
                vis_list = vis if isinstance(vis, list) else [vis] if isinstance(vis, str) else []

                for img in vis_list:
                    img_path = img.get("path") if isinstance(img, dict) else str(img)
                    img_base64 = img.get("base64") if isinstance(img, dict) else None
                    
                    # Cek apakah image sudah ada di list
                    if not any(x.get("path") == img_path for x in images if isinstance(x, dict)):
                        # Ambil potongan teks chunk asli sebagai konteks visual gambar (max 600 chars)
                        context_snippet = t.get("text", "")[:600]
                        img_id = f"IMG-{len(images)+1:03d}"
                        images.append({
                            "id": img_id,
                            "path": img_path,
                            "base64": img_base64,
                            "context": context_snippet
                        })

        return {
            "text": [{"text": t.get("expanded_text", t["text"]), "source_file": t["source_file"], "visual_context": t.get("metadata", {}).get("has_visual_content", [])} for t in texts],
            "images": images
        }

    @staticmethod
    async def _search_with_book_reference(query: str, k_text: int, mapel: Optional[str], kelas: Optional[int], buku_id: str) -> list:
        """Dual-search parallel: default + spesifik buku (by buku_id), lalu merge & dedup dengan prioritas buku."""
        default_texts, book_texts = await asyncio.gather(
            retrieve_text(query, top_k=k_text, mata_pelajaran=mapel, kelas=kelas),
            retrieve_text(query, top_k=k_text, mata_pelajaran=mapel, kelas=kelas, buku_id=buku_id),
        )

        seen_ids = set()
        merged = []
        for t in book_texts + default_texts:
            doc_id = t.get("id") or hash(t.get("text", ""))
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            merged.append(t)

        return merged[:k_text]

# ================================================================
# 7. Utilities
# ================================================================
def _fix_json_escapes(s: str) -> str:
    r"""
    Fix invalid backslash escapes in a JSON string before parsing.
    LLMs frequently output LaTeX commands like \cdot with only a single backslash.
    """
    result = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == '\\':
            if i + 1 < n:
                next_char = s[i + 1]
                if next_char in ('"', '/', 'b', 'f', 'n', 'r', 't'):
                    result.append(s[i])
                    result.append(next_char)
                    i += 2
                elif next_char == '\\':
                    result.append('\\')
                    result.append('\\')
                    i += 2
                elif next_char == 'u':
                    if i + 5 < n and re.match(r'[0-9a-fA-F]{4}', s[i+2:i+6]):
                        result.append(s[i:i+6])
                        i += 6
                    else:
                        result.append('\\\\')
                        i += 1
                else:
                    result.append('\\\\')
                    i += 1
            else:
                result.append('\\\\')
                i += 1
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)

def truncate_context_to_budget(text: str, max_tokens: int = 4000, chars_per_token: int = 4) -> str:
    """
    Memotong teks context agar tidak memakan terlalu banyak token input.
    """
    if not text:
        return text

    max_chars = max_tokens * chars_per_token
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.5:
        truncated = truncated[:last_period + 1]

    return truncated + "\n\n[INFO: Teks referensi dipotong karena batas token]"

def clean_json_from_llm(raw_text: str | list) -> dict | list:
    # 0. Handle LangChain message content blocks (e.g., from Vision models or VLLM)
    if isinstance(raw_text, list):
        # Extract text from blocks: [{"type": "text", "text": "{...}"}]
        extracted_text = ""
        for block in raw_text:
            if isinstance(block, dict) and "text" in block:
                extracted_text += block["text"]
            elif isinstance(block, str):
                extracted_text += block
        raw_text = extracted_text
    elif isinstance(raw_text, str):
        # Sometimes it comes as a stringified list of blocks!
        if raw_text.strip().startswith('[{"type":') or raw_text.strip().startswith('[{"text":'):
            try:
                blocks = json.loads(raw_text)
                if isinstance(blocks, list) and len(blocks) > 0 and isinstance(blocks[0], dict) and "text" in blocks[0]:
                    raw_text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
            except Exception:
                pass

    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    raw_text = _fix_json_escapes(raw_text)

    # 1. Coba cari di dalam markdown block ```json ... ```
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw_text, re.DOTALL)
    if match:
        clean_text = match.group(1).strip()
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            pass

    # 2. Kalau gak ada markdown block, bersihkan teks
    clean_text = re.sub(r'```(?:json)?', '', raw_text).strip()

    # Cari batas awal dan akhir dari kemungkian Dict atau List
    first_brace = clean_text.find('{')
    last_brace = clean_text.rfind('}')
    first_bracket = clean_text.find('[')
    last_bracket = clean_text.rfind(']')

    candidates = []
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(clean_text[first_brace:last_brace+1])
    if first_bracket != -1 and last_bracket != -1 and first_bracket < last_bracket:
        candidates.append(clean_text[first_bracket:last_bracket+1])

    # Urutkan berdasarkan panjang string menurun (coba box JSON terbesar lebih dulu)
    candidates.sort(key=len, reverse=True)

    for text in candidates:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 3. Coba perbaiki jika model menghasilkan multiple JSON terpisah (seperti `{"text": ...}\n{"judul": ...}`)
    # Kita cari semua pola {...} yang valid dan gabungkan key-nya
    # Ambil semua teks yang diapit kurawal terluar (ini tidak sempurna jika nested, tapi cukup baik untuk fallback)
    potential_blocks = []
    depth = 0
    start_idx = -1
    for i, char in enumerate(clean_text):
        if char == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0 and start_idx != -1:
                potential_blocks.append(clean_text[start_idx:i+1])
                start_idx = -1

    if len(potential_blocks) > 1:
        merged_dict = {}
        success_merge = False
        for block in potential_blocks:
            try:
                parsed = json.loads(block)
                if isinstance(parsed, dict):
                    merged_dict.update(parsed)
                    success_merge = True
            except json.JSONDecodeError:
                pass
        if success_merge:
            return merged_dict

    # Jika semua gagal, kembalikan seluruh teks asli secara penuh agar frontend/klien bisa mendebug
    return {"error": "Gagal parsing JSON dari LLM", "raw": raw_text}

def generate_konten_id(tipe: str, level: str, materi_id: str, kelas_id: str = "all") -> str:
    lvl_str = (level or "all").lower()
    mat_clean = materi_id.split("__")[-1] if "__" in materi_id else materi_id
    kls_str = (kelas_id or "all").lower()
    return f"konten_{mat_clean}_{tipe}_{lvl_str}_{kls_str}_{int(time.time())}"