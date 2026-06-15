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
QDRANT_HOST        = os.getenv("QDRANT_HOST")
if QDRANT_HOST.startswith("http://"):
    QDRANT_HOST = QDRANT_HOST[7:]
elif QDRANT_HOST.startswith("https://"):
    QDRANT_HOST = QDRANT_HOST[8:]
QDRANT_PORT        = int(os.getenv("QDRANT_PORT", 6333))
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
    model = get_sentence_model()
    prefixed = f"query: {query.strip()}"
    loop = asyncio.get_event_loop()
    vector = await loop.run_in_executor(None, lambda: model.encode([prefixed], normalize_embeddings=True, convert_to_numpy=True)[0])
    return vector.tolist()

# ================================================================
# 2. Qdrant Search Engine
# ================================================================
def _search_qdrant_dense(collection: str, vector: list, top_k: int, filter_payload: Optional[dict] = None) -> list:
    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection}/points/search"
    payload = {"vector": {"name": "dense", "vector": vector}, "limit": top_k, "with_payload": True}
    if filter_payload:
        payload["filter"] = filter_payload
    try:
        response = requests.post(url, json=payload, timeout=120)

        # Fallback ke vector biasa jika collection tidak pakai named vectors (seperti srma-22)
        if response.status_code == 400 and "Not existing vector name error" in response.text:
            payload["vector"] = vector
            response = requests.post(url, json=payload, timeout=120)

        if response.status_code != 200:
            print(f"⚠️ Qdrant Dense Error Body: {response.text}")

        response.raise_for_status()
        return response.json().get("result", [])
    except Exception as e:
        print(f"❌ Error query Qdrant Dense: {e}")
        return []

# ── Hybrid-only components (tidak dipakai saat SEARCH_MODE=dense) ──────────

def _search_qdrant_splade(collection: str, query: str, top_k: int, filter_payload: Optional[dict] = None) -> list:
    model = get_sparse_model()
    sparse_vector = model.encode_query(query)

    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection}/points/search"
    payload = {
        "vector": {"name": "sparse", "vector": sparse_vector},
        "limit": top_k,
        "with_payload": True
    }
    if filter_payload:
        payload["filter"] = filter_payload
    try:
        response = requests.post(url, json=payload, timeout=120)

        if response.status_code != 200:
            print(f"⚠️ Qdrant Splade Error Body: {response.text}")

        response.raise_for_status()
        hits = response.json().get("result", [])

        results = []
        for hit in hits:
            payload_data = hit.get("payload", {})
            metadata = payload_data.get("metadata", {})
            results.append({
                "score": hit.get("score", 0.0),
                "text": payload_data.get("text", payload_data.get("page_content", "N/A")),
                "metadata": metadata,
                "source_file": payload_data.get("source_file", metadata.get("source_file", "N/A")),
                "retrieval_type": "splade"
            })
        return results
    except Exception as e:
        print(f"❌ Error query Qdrant Splade: {e}")
        return []

def _scroll_qdrant(collection: str, scroll_filter: dict, limit: int = 200) -> list:
    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{collection}/points/scroll"
    payload = {"filter": scroll_filter, "limit": limit, "with_payload": True}
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("result", {}).get("points", [])
    except Exception as e:
        print(f"❌ Error scroll Qdrant: {e}")
        return []

def _build_qdrant_filter(asset_type: Optional[str] = None, source: Optional[str] = None, mata_pelajaran: Optional[str] = None, kelas: Optional[int] = None) -> Optional[dict]:
    conditions = []
    if asset_type: conditions.append({"key": "asset_type", "match": {"value": asset_type}})
    if source: conditions.append({"key": "source", "match": {"value": source}})
    if mata_pelajaran: conditions.append({"key": "mata_pelajaran", "match": {"value": mata_pelajaran}})
    if kelas is not None: conditions.append({"key": "kelas", "match": {"value": kelas}})
    return {"must": conditions} if conditions else None

# ================================================================
# 3. BM25 Sparse Search  (hybrid only)
# ================================================================
def build_bm25_index():
    global _bm25, _bm25_docs
    if _bm25 is not None:
        return

    if BM25_CACHE_PATH.exists():
        print(f"📦 Loading BM25 dari cache: {BM25_CACHE_PATH}")
        with open(BM25_CACHE_PATH, "rb") as f:
            cache = pickle.load(f)
        _bm25 = cache["bm25"]
        _bm25_docs = cache["docs"]
        return

    print("⏳ Building BM25 index dari Qdrant (pertama kali)...")
    url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{TEXT_COLLECTION}/points/scroll"
    all_points = []
    offset = None

    while True:
        payload = {"limit": 1000, "with_payload": True}
        if offset is not None:
            payload["offset"] = offset
        try:
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json().get("result", {})
            points = data.get("points", [])
            all_points.extend(points)
            offset = data.get("next_page_offset")
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
        metadata = payload.get("metadata", {})
        docs.append({
            "text": text,
            "metadata": metadata,
            "source_file": payload.get("source_file", metadata.get("source_file", "N/A"))
        })
        corpus.append(tokenize(text))

    if corpus:
        _bm25 = BM25Okapi(corpus)
        _bm25_docs = docs
        with open(BM25_CACHE_PATH, "wb") as f:
            pickle.dump({"bm25": _bm25, "docs": _bm25_docs}, f)
        print(f"✅ BM25 index built & cached: {len(docs)} docs")
    else:
        print("⚠ Tidak ada dokumen untuk BM25.")

def sparse_search(query: str, top_k: int = 10, mata_pelajaran: Optional[str] = None, kelas: Optional[int] = None):
    build_bm25_index()
    if _bm25 is None: return []

    tokenized_query = tokenize(query)
    scores = _bm25.get_scores(tokenized_query)
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    results = []
    for idx in ranked_idx:
        doc = dict(_bm25_docs[idx])
        # Soft-filter matching untuk mapel & kelas karena BM25 ditarik full corpus
        meta = doc.get("metadata", {})
        if mata_pelajaran and meta.get("mata_pelajaran") != mata_pelajaran:
            continue
        if kelas is not None and meta.get("kelas") != kelas:
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

def expand_chunk_context(docs: list, window=1) -> list:
    expanded_docs = []
    for doc in docs:
        metadata = doc.get("metadata", {})
        chunk_index = metadata.get("chunk_index")
        source_file = doc.get("source_file")
        if chunk_index is None:
            doc["expanded_text"] = doc["text"]
            expanded_docs.append(doc)
            continue

        cache_key = (source_file, chunk_index, window)
        if cache_key in _chunk_expansion_cache:
            doc["expanded_text"] = _chunk_expansion_cache[cache_key]
            expanded_docs.append(doc)
            continue

        min_idx = chunk_index - window
        max_idx = chunk_index + window

        points = _scroll_qdrant(TEXT_COLLECTION, scroll_filter={"must": [{"key": "source_file", "match": {"value": source_file}}]})
        chunks = []
        for p in points:
            payload = p.get("payload", {})
            meta = payload.get("metadata", {})
            idx = meta.get("chunk_index")
            if idx is not None and min_idx <= idx <= max_idx:
                text = payload.get("text", payload.get("page_content", ""))
                if text: chunks.append((idx, text))

        chunks.sort(key=lambda x: x[0])
        expanded_text = "\n".join(text for _, text in chunks) if chunks else doc["text"]
        _chunk_expansion_cache[cache_key] = expanded_text
        doc["expanded_text"] = expanded_text
        expanded_docs.append(doc)
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
async def _retrieve_dense(query: str, top_k: int, mata_pelajaran: Optional[str], kelas: Optional[int]) -> list:
    """
    Dense-only retrieval: embed → Qdrant dense search → dedup.
    Tidak menjalankan SPLADE, BM25, RRF, maupun reranker sehingga
    lebih ringan dan cepat untuk production.
    """
    retrieve_k = max(top_k * 3, 20)

    vector = await embed_text_for_text_vdb(query)
    payload_filter = _build_qdrant_filter(mata_pelajaran=mata_pelajaran, kelas=kelas)
    hits = _search_qdrant_dense(TEXT_COLLECTION, vector, retrieve_k, filter_payload=payload_filter)

    results = []
    for hit in hits:
        payload = hit.get("payload", {})
        metadata = payload.get("metadata", {})
        results.append({
            "score": hit.get("score", 0.0),
            "text": payload.get("text", payload.get("page_content", "N/A")),
            "metadata": metadata,
            "source_file": payload.get("source_file", metadata.get("source_file", "N/A")),
            "retrieval_type": "dense",
        })

    unique_results = deduplicate(results)
    # Kembalikan top_k teratas (sudah diurutkan Qdrant by score)
    return unique_results[:top_k]


async def _retrieve_hybrid(query: str, top_k: int, mata_pelajaran: Optional[str], kelas: Optional[int]) -> list:
    """
    Hybrid retrieval: Dense + SPLADE + BM25 → RRF fusion → dedup
    → chunk expansion → rerank.
    Lebih akurat namun lebih berat — gunakan saat infrastruktur siap.
    """
    retrieve_k = max(top_k * 5, 30)

    # 1. Dense Search
    vector = await embed_text_for_text_vdb(query)
    payload_filter = _build_qdrant_filter(mata_pelajaran=mata_pelajaran, kelas=kelas)
    hits = _search_qdrant_dense(TEXT_COLLECTION, vector, retrieve_k, filter_payload=payload_filter)
    dense_results = []
    for hit in hits:
        payload = hit.get("payload", {})
        metadata = payload.get("metadata", {})
        dense_results.append({
            "score": hit.get("score", 0.0),
            "text": payload.get("text", payload.get("page_content", "N/A")),
            "metadata": metadata,
            "source_file": payload.get("source_file", metadata.get("source_file", "N/A")),
            "retrieval_type": "dense"
        })

    # 2. Sparse Search (SPLADE & BM25)
    splade_results = _search_qdrant_splade(TEXT_COLLECTION, query, top_k=retrieve_k, filter_payload=payload_filter)
    bm25_results = sparse_search(query, top_k=retrieve_k, mata_pelajaran=mata_pelajaran, kelas=kelas)

    # 3. RRF + Dedup + Expand
    fused_results = reciprocal_rank_fusion(dense_results, splade_results, bm25_results)
    unique_results = deduplicate(fused_results)
    expanded_results = expand_chunk_context(unique_results, window=1)

    # 4. Rerank
    reranked_results = await rerank_results(query, expanded_results, top_k=top_k)
    return reranked_results


async def retrieve_text(query: str, top_k: int = 5, mata_pelajaran: Optional[str] = None, kelas: Optional[int] = None) -> list:
    """
    Entry point retrieval. Memilih strategi berdasarkan SEARCH_MODE:
      - "dense"  → _retrieve_dense()   (default production)
      - "hybrid" → _retrieve_hybrid()  (aktifkan saat siap)
    """
    if not query.strip():
        return []

    if SEARCH_MODE == "hybrid":
        return await _retrieve_hybrid(query, top_k, mata_pelajaran, kelas)
    else:
        return await _retrieve_dense(query, top_k, mata_pelajaran, kelas)

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
    async def unified_search(query: str, tipe: str, mapel: Optional[str] = None, kelas: Optional[int] = None) -> Dict[str, Any]:
        """Perform full pipeline search with dynamic chunk sizing and multimodal metadata capabilities."""
        k_text = RAGEngine.get_k_for_type(tipe)
        texts = await retrieve_text(query, top_k=k_text, mata_pelajaran=mapel, kelas=kelas)

        images = []
        if tipe in ["quiz_pg", "quiz_essay", "bacaan"]:
            for t in texts:
                vis = t.get("metadata", {}).get("has_visual_content", [])
                vis_list = vis if isinstance(vis, list) else [vis] if isinstance(vis, str) else []

                for img in vis_list:
                    # img bisa berupa string (path) atau dict (path, base64, dll)
                    img_path = img.get("path") if isinstance(img, dict) else img
                    
                    # Cek apakah image sudah ada di list
                    if not any(x["path"] == img_path for x in images if isinstance(x, dict)):
                        # Ambil potongan teks chunk asli sebagai konteks visual gambar (max 600 chars)
                        context_snippet = t.get("text", "")[:600]
                        
                        img_entry = {
                            "path": img_path,
                            "context": context_snippet
                        }
                        
                        # Simpan base64 jika ada agar bisa digunakan frontend
                        if isinstance(img, dict):
                            if "base64" in img:
                                img_entry["base64"] = img["base64"]
                            if "mime_type" in img:
                                img_entry["mime_type"] = img["mime_type"]
                                
                        images.append(img_entry)

        return {
            "text": [{"text": t.get("expanded_text", t["text"]), "source_file": t["source_file"], "visual_context": t.get("metadata", {}).get("has_visual_content", [])} for t in texts],
            "images": images
        }

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

def clean_json_from_llm(raw_text: str) -> dict | list:
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