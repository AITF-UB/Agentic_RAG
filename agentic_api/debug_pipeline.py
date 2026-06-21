# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║              DEBUG PIPELINE & RETRIEVER SYSTEM                   ║
║  Test upload → ingest → retrieve cycle dengan collection debug   ║
╚══════════════════════════════════════════════════════════════════╝

Script ini terpisah dari collection utama (hybrid_new).
Menggunakan collection debug khusus untuk testing.

Cara pakai:
  python debug_pipeline.py                       # Jalankan semua test
  python debug_pipeline.py --test upload         # Test upload saja
  python debug_pipeline.py --test payload        # Inspect payload Qdrant
  python debug_pipeline.py --test retrieve       # Test retrieval saja
  python debug_pipeline.py --test filter         # Test filter buku_id vs source_file
  python debug_pipeline.py --test cleanup        # Hapus collection debug
  python debug_pipeline.py --pdf path/to/file.pdf  # Upload PDF spesifik
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════════
# KONFIGURASI DEBUG
# ══════════════════════════════════════════════════════════════════

API_BASE_URL    = os.getenv("DEBUG_API_URL", "http://localhost:8000")
API_KEY         = os.getenv("API_KEY", "")
QDRANT_HOST     = os.getenv("QDRANT_HOST", "76.13.195.1")
QDRANT_PORT     = int(os.getenv("QDRANT_PORT", "6333"))

# Collection debug — TERPISAH dari collection utama
DEBUG_COLLECTION = os.getenv("DEBUG_COLLECTION", "debug_pipeline_test")
MAIN_COLLECTION  = os.getenv("QDRANT_TEXT_COLLECTION", "hybrid_new")

# Pastikan host tanpa http prefix untuk Qdrant REST
_qdrant_host = QDRANT_HOST
if _qdrant_host.startswith("http://"):
    _qdrant_host = _qdrant_host[7:]
elif _qdrant_host.startswith("https://"):
    _qdrant_host = _qdrant_host[8:]

QDRANT_BASE = f"http://{_qdrant_host}:{QDRANT_PORT}"


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _sep(title: str = "", char: str = "═", width: int = 64):
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{char * pad} {title} {char * (width - pad - len(title) - 2)}")
    else:
        print(char * width)


def ok(msg):    print(f"  ✅  {msg}")
def warn(msg):  print(f"  ⚠️   {msg}")
def err(msg):   print(f"  ❌  {msg}")
def info(msg):  print(f"  ℹ️   {msg}")
def dim(msg):   print(f"      {msg}")


def _api_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _api_headers_form() -> dict:
    h = {}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _qdrant_url(path: str) -> str:
    return f"{QDRANT_BASE}{path}"


def _pp_json(data, indent=2, max_str_len=200):
    """Pretty-print JSON dengan truncation untuk string panjang (base64, dll)."""
    def _truncate(obj):
        if isinstance(obj, str) and len(obj) > max_str_len:
            return obj[:max_str_len] + f"... ({len(obj)} chars)"
        if isinstance(obj, dict):
            return {k: _truncate(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_truncate(v) for v in obj]
        return obj
    print(json.dumps(_truncate(data), indent=indent, ensure_ascii=False))


# ══════════════════════════════════════════════════════════════════
# TEST 1 — HEALTH CHECK
# ══════════════════════════════════════════════════════════════════

def test_health():
    _sep("TEST: HEALTH CHECK")

    # API Health
    info("Checking API server...")
    try:
        r = requests.get(f"{API_BASE_URL}/health", headers=_api_headers(), timeout=10)
        if r.status_code == 200:
            data = r.json()
            ok(f"API server OK — pipeline_available={data.get('pipeline_available')}")
            info(f"Active jobs: {data.get('active_jobs')}, Total jobs: {data.get('total_jobs')}")
        else:
            err(f"API health HTTP {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        err(f"Tidak bisa konek ke API server di {API_BASE_URL}")
        warn("Pastikan uvicorn sudah running: uvicorn main:app --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        err(f"Health check error: {e}")
        return False

    # Qdrant Health
    info("Checking Qdrant...")
    try:
        r = requests.get(f"{QDRANT_BASE}/collections", timeout=10)
        if r.status_code == 200:
            collections = [c["name"] for c in r.json().get("result", {}).get("collections", [])]
            ok(f"Qdrant OK — {len(collections)} collections")
            for c in collections:
                marker = " ← MAIN" if c == MAIN_COLLECTION else (" ← DEBUG" if c == DEBUG_COLLECTION else "")
                info(f"  • {c}{marker}")

            if DEBUG_COLLECTION in collections:
                ok(f"Debug collection '{DEBUG_COLLECTION}' sudah ada")
            else:
                warn(f"Debug collection '{DEBUG_COLLECTION}' belum ada (akan dibuat saat upload)")
        else:
            err(f"Qdrant HTTP {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        err(f"Tidak bisa konek ke Qdrant di {QDRANT_BASE}")
        return False

    return True


# ══════════════════════════════════════════════════════════════════
# TEST 2 — UPLOAD PDF VIA API
# ══════════════════════════════════════════════════════════════════

def test_upload(pdf_path: Optional[str] = None, buku_id: Optional[str] = None) -> Optional[dict]:
    _sep("TEST: UPLOAD PDF → PIPELINE")

    # Cari PDF untuk test
    if pdf_path is None:
        # Cari PDF di folder uploads/
        uploads_dir = Path(__file__).parent / "uploads"
        pdfs = list(uploads_dir.glob("*.pdf")) if uploads_dir.exists() else []
        if pdfs:
            pdf_path = str(pdfs[0])
            info(f"Menggunakan PDF dari uploads/: {pdfs[0].name}")
        else:
            err("Tidak ada PDF untuk test. Gunakan --pdf path/to/file.pdf")
            return None
    else:
        if not Path(pdf_path).exists():
            err(f"File tidak ditemukan: {pdf_path}")
            return None
        info(f"Menggunakan PDF: {pdf_path}")

    # Generate buku_id untuk test
    if buku_id is None:
        buku_id = f"debug-{uuid.uuid4().hex[:8]}"
    info(f"buku_id: {buku_id}")
    info(f"Target collection: {DEBUG_COLLECTION}")

    # Upload ke API
    info("Uploading...")
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (Path(pdf_path).name, f, "application/pdf")}
            data = {
                "buku_id":         buku_id,
                "mata_pelajaran":  "debug_test",
                "id_kelas":        "99",
                "jenjang":         "DEBUG",
                "id_guru":         "debug_guru",
            }
            # Override collection ke debug collection via env
            # (collection diambil dari QDRANT_PIPELINE_EKSTRACTION env)
            r = requests.post(
                f"{API_BASE_URL}/pipeline/upload",
                files=files,
                data=data,
                headers=_api_headers_form(),
                timeout=30,
            )

        if r.status_code == 202:
            job = r.json()
            ok(f"Upload berhasil — job_id: {job['job_id']}")
            info(f"Status: {job['status']}")

            # Poll job sampai selesai
            return _poll_job(job["job_id"], buku_id)
        else:
            err(f"Upload gagal HTTP {r.status_code}")
            dim(r.text[:500])
            return None

    except Exception as e:
        err(f"Upload error: {e}")
        return None


def _poll_job(job_id: str, buku_id: str, timeout: int = 300) -> Optional[dict]:
    """Poll job status sampai selesai atau timeout."""
    info(f"Polling job {job_id[:8]}... (timeout {timeout}s)")
    start = time.time()
    last_status = ""

    while time.time() - start < timeout:
        try:
            r = requests.get(
                f"{API_BASE_URL}/pipeline/job/{job_id}",
                headers=_api_headers(),
                timeout=10,
            )
            if r.status_code != 200:
                time.sleep(3)
                continue

            job = r.json()
            status = job.get("status")

            if status != last_status:
                info(f"  Status: {status} — {job.get('message', '')}")
                last_status = status

            if status == "success":
                result = job.get("result", {})
                ok("Pipeline SELESAI!")
                info(f"  buku_id (result):    {result.get('buku_id')}")
                info(f"  source_file (result): {result.get('source_file')}")
                info(f"  total_chunks: {result.get('total_chunks')}")
                info(f"  collection:   {result.get('qdrant_collection')}")

                # Validasi buku_id
                if result.get("buku_id") == buku_id:
                    ok(f"buku_id di result COCOK: {buku_id}")
                else:
                    err(f"buku_id MISMATCH! Expected={buku_id}, Got={result.get('buku_id')}")

                return {"job": job, "buku_id": buku_id, "result": result}

            elif status == "failed":
                err(f"Pipeline GAGAL: {job.get('error', '')[:300]}")
                return None

        except Exception as e:
            warn(f"Poll error: {e}")

        time.sleep(3)

    err(f"Timeout setelah {timeout}s")
    return None


# ══════════════════════════════════════════════════════════════════
# TEST 3 — INSPECT QDRANT PAYLOAD
# ══════════════════════════════════════════════════════════════════

def test_inspect_payload(collection: Optional[str] = None, buku_id: Optional[str] = None):
    _sep("TEST: INSPECT QDRANT PAYLOAD")

    col = collection or DEBUG_COLLECTION
    info(f"Collection: {col}")

    # Cek collection ada
    try:
        r = requests.get(_qdrant_url(f"/collections/{col}"), timeout=10)
        if r.status_code != 200:
            err(f"Collection '{col}' tidak ditemukan")
            return False
        col_info = r.json().get("result", {})
        points_count = col_info.get("points_count", 0)
        info(f"Total points: {points_count}")
    except Exception as e:
        err(f"Error: {e}")
        return False

    if points_count == 0:
        warn("Collection kosong — upload PDF dulu")
        return False

    # Scroll beberapa points
    scroll_body = {
        "limit": 5,
        "with_payload": True,
        "with_vector": False,
    }

    # Filter by buku_id jika diberikan
    if buku_id:
        scroll_body["filter"] = {
            "must": [{"key": "buku_id", "match": {"value": buku_id}}]
        }
        info(f"Filter: buku_id = {buku_id}")

    try:
        r = requests.post(
            _qdrant_url(f"/collections/{col}/points/scroll"),
            json=scroll_body,
            timeout=30,
        )
        r.raise_for_status()
        points = r.json().get("result", {}).get("points", [])

        if not points:
            if buku_id:
                err(f"Tidak ada points dengan buku_id={buku_id}")
                warn("Kemungkinan buku_id tidak disimpan saat ingest")
            else:
                err("Tidak ada points ditemukan")
            return False

        ok(f"Ditemukan {len(points)} points (sample)")

        for i, pt in enumerate(points):
            payload = pt.get("payload", {})
            print()
            info(f"── Point #{i+1} (id: {pt.get('id', '?')}) ──")

            # Cek field-field kunci
            fields_to_check = [
                ("buku_id",          payload.get("buku_id")),
                ("source_file",      payload.get("source_file")),
                ("mata_pelajaran",   payload.get("mata_pelajaran")),
                ("id_kelas",         payload.get("id_kelas")),
                ("jenjang",          payload.get("jenjang")),
                ("id_guru",          payload.get("id_guru")),
                ("page",             payload.get("page")),
                ("chunk_index",      payload.get("chunk_index")),
                ("chapter",          payload.get("chapter")),
                ("has_visual_content", "✓" if payload.get("has_visual_content") else "✗"),
            ]

            for name, val in fields_to_check:
                status_icon = "✅" if val is not None and val != "" else "⬜"
                dim(f"  {status_icon} {name:25s} = {val}")

            # Preview teks
            text = payload.get("page_content", "")[:150]
            dim(f"  📝 page_content (preview) = {text}...")

        # Validasi pemisahan buku_id vs source_file
        _sep("VALIDASI PEMISAHAN buku_id vs source_file", "─")
        sample = points[0].get("payload", {})
        has_buku_id = "buku_id" in sample and sample["buku_id"] is not None
        has_source_file = "source_file" in sample and sample["source_file"] is not None

        if has_buku_id and has_source_file:
            if sample["buku_id"] != sample["source_file"]:
                ok(f"buku_id TERPISAH dari source_file ✓")
                info(f"  buku_id     = {sample['buku_id']}")
                info(f"  source_file = {sample['source_file']}")
            else:
                warn(f"buku_id == source_file (mungkin masih data lama)")
                info(f"  Keduanya = {sample['buku_id']}")
        elif has_buku_id and not has_source_file:
            warn("Ada buku_id tapi source_file missing")
        elif not has_buku_id and has_source_file:
            err("buku_id TIDAK ADA di payload! Field baru belum disimpan saat ingest.")
            warn("Pastikan pipeline sudah menggunakan kode terbaru (full_pipeline.py)")
        else:
            err("Baik buku_id maupun source_file TIDAK ADA di payload")

        return True

    except Exception as e:
        err(f"Error inspecting: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
# TEST 4 — TEST RETRIEVAL (via Qdrant langsung)
# ══════════════════════════════════════════════════════════════════

def test_retrieve(collection: Optional[str] = None, query: str = "sistem saraf somatosensory"):
    _sep("TEST: RETRIEVAL via Qdrant")

    col = collection or DEBUG_COLLECTION
    info(f"Collection: {col}")
    info(f"Query: \"{query}\"")

    # Embed query
    info("Embedding query dengan dense model...")
    try:
        from model_registry import get_dense_model
        model = get_dense_model()
        vector = model.encode(
            [f"query: {query}"],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0].tolist()
        ok(f"Embedding berhasil (dim={len(vector)})")
    except ImportError:
        err("Tidak bisa import model_registry — jalankan dari folder agentic_api/")
        info("Fallback: skip embedding test, lanjut scroll test")
        return _test_scroll_retrieval(col)
    except Exception as e:
        err(f"Embedding error: {e}")
        return False

    # Dense search tanpa filter
    _sep("A. Dense Search TANPA filter", "─")
    results_no_filter = _dense_search(col, vector, top_k=5, qdrant_filter=None)
    if results_no_filter:
        ok(f"Ditemukan {len(results_no_filter)} results")
        for r in results_no_filter[:3]:
            payload = r.get("payload", {})
            dim(f"  score={r.get('score', 0):.4f}  buku_id={payload.get('buku_id', 'N/A'):30s}  source={payload.get('source_file', 'N/A')}")
            dim(f"    text: {payload.get('page_content', '')[:100]}...")
    else:
        warn("Tidak ada result tanpa filter")

    # Dense search DENGAN filter buku_id
    _sep("B. Dense Search DENGAN filter buku_id", "─")
    # Cari buku_id yang ada di collection
    buku_ids = _get_unique_buku_ids(col)
    if buku_ids:
        test_buku_id = buku_ids[0]
        info(f"Filter buku_id = {test_buku_id}")
        filter_body = {"must": [{"key": "buku_id", "match": {"value": test_buku_id}}]}
        results_with_filter = _dense_search(col, vector, top_k=5, qdrant_filter=filter_body)
        if results_with_filter:
            ok(f"Ditemukan {len(results_with_filter)} results dengan filter buku_id")
            for r in results_with_filter[:3]:
                payload = r.get("payload", {})
                dim(f"  score={r.get('score', 0):.4f}  buku_id={payload.get('buku_id', 'N/A')}")
        else:
            warn(f"Tidak ada result untuk buku_id={test_buku_id}")
    else:
        warn("Tidak ada buku_id di collection — field mungkin belum ada")

    # Dense search DENGAN filter source_file
    _sep("C. Dense Search DENGAN filter source_file", "─")
    sources = _get_unique_source_files(col)
    if sources:
        test_source = sources[0]
        info(f"Filter source_file = {test_source}")
        filter_body = {"must": [{"key": "source_file", "match": {"value": test_source}}]}
        results_source = _dense_search(col, vector, top_k=5, qdrant_filter=filter_body)
        if results_source:
            ok(f"Ditemukan {len(results_source)} results dengan filter source_file")
        else:
            warn(f"Tidak ada result untuk source_file={test_source}")
    else:
        warn("Tidak ada source_file unik ditemukan")

    return True


def _dense_search(collection: str, vector: list, top_k: int = 5, qdrant_filter: Optional[dict] = None) -> list:
    """Langsung search ke Qdrant tanpa lewat API."""
    body: dict = {
        "vector": {"name": "dense", "vector": vector},
        "limit": top_k,
        "with_payload": True,
    }
    if qdrant_filter:
        body["filter"] = qdrant_filter
    try:
        r = requests.post(
            _qdrant_url(f"/collections/{collection}/points/search"),
            json=body,
            timeout=30,
        )
        if r.status_code == 400 and "Not existing vector name" in r.text:
            # Fallback: unnamed vector
            body["vector"] = vector
            r = requests.post(
                _qdrant_url(f"/collections/{collection}/points/search"),
                json=body,
                timeout=30,
            )
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as e:
        err(f"Dense search error: {e}")
        return []


def _test_scroll_retrieval(collection: str) -> bool:
    """Fallback: test retrieval via scroll (tanpa embedding)."""
    info("Scroll test (tanpa embedding)...")
    try:
        r = requests.post(
            _qdrant_url(f"/collections/{collection}/points/scroll"),
            json={"limit": 5, "with_payload": True, "with_vector": False},
            timeout=30,
        )
        r.raise_for_status()
        points = r.json().get("result", {}).get("points", [])
        if points:
            ok(f"Scroll berhasil — {len(points)} points")
            return True
        else:
            warn("Collection kosong")
            return False
    except Exception as e:
        err(f"Scroll error: {e}")
        return False


def _get_unique_buku_ids(collection: str) -> list:
    """Ambil daftar buku_id unik dari collection."""
    try:
        r = requests.post(
            _qdrant_url(f"/collections/{collection}/points/scroll"),
            json={"limit": 100, "with_payload": {"include": ["buku_id"]}, "with_vector": False},
            timeout=30,
        )
        r.raise_for_status()
        points = r.json().get("result", {}).get("points", [])
        ids = set()
        for p in points:
            bid = p.get("payload", {}).get("buku_id")
            if bid:
                ids.add(bid)
        return sorted(ids)
    except Exception:
        return []


def _get_unique_source_files(collection: str) -> list:
    """Ambil daftar source_file unik dari collection."""
    try:
        r = requests.post(
            _qdrant_url(f"/collections/{collection}/points/scroll"),
            json={"limit": 100, "with_payload": {"include": ["source_file"]}, "with_vector": False},
            timeout=30,
        )
        r.raise_for_status()
        points = r.json().get("result", {}).get("points", [])
        sources = set()
        for p in points:
            sf = p.get("payload", {}).get("source_file")
            if sf:
                sources.add(sf)
        return sorted(sources)
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════
# TEST 5 — FILTER COMPARISON (buku_id vs source_file)
# ══════════════════════════════════════════════════════════════════

def test_filter_comparison(collection: Optional[str] = None):
    _sep("TEST: FILTER COMPARISON (buku_id vs source_file)")

    col = collection or DEBUG_COLLECTION
    info(f"Collection: {col}")

    buku_ids = _get_unique_buku_ids(col)
    source_files = _get_unique_source_files(col)

    print()
    info(f"Unique buku_id      : {buku_ids if buku_ids else '(tidak ada)'}")
    info(f"Unique source_file  : {source_files if source_files else '(tidak ada)'}")

    if not buku_ids and not source_files:
        err("Tidak ada data untuk dibandingkan")
        return False

    # Test: filter by buku_id saja
    if buku_ids:
        _sep("A. Count per buku_id", "─")
        for bid in buku_ids:
            count = _count_by_filter(col, "buku_id", bid)
            info(f"  buku_id={bid:40s}  →  {count} points")

    # Test: filter by source_file saja
    if source_files:
        _sep("B. Count per source_file", "─")
        for sf in source_files:
            count = _count_by_filter(col, "source_file", sf)
            info(f"  source_file={sf:36s}  →  {count} points")

    # Cross-validation: sama buku_id, beda source_file?
    if buku_ids and source_files:
        _sep("C. Cross-validation", "─")
        for bid in buku_ids:
            # Ambil source_files yang terkait dengan buku_id ini
            try:
                r = requests.post(
                    _qdrant_url(f"/collections/{col}/points/scroll"),
                    json={
                        "filter": {"must": [{"key": "buku_id", "match": {"value": bid}}]},
                        "limit": 100,
                        "with_payload": {"include": ["source_file", "buku_id"]},
                        "with_vector": False,
                    },
                    timeout=30,
                )
                r.raise_for_status()
                points = r.json().get("result", {}).get("points", [])
                related_sources = set(p.get("payload", {}).get("source_file", "?") for p in points)
                info(f"  buku_id={bid[:30]:30s}  ↔  source_files={related_sources}")

                if len(related_sources) == 1:
                    sf = list(related_sources)[0]
                    if sf != bid:
                        ok(f"    buku_id ≠ source_file → Pemisahan BENAR ✓")
                    else:
                        warn(f"    buku_id == source_file → Mungkin data lama")
            except Exception as e:
                err(f"  Error: {e}")

    return True


def _count_by_filter(collection: str, key: str, value: str) -> int:
    try:
        r = requests.post(
            _qdrant_url(f"/collections/{collection}/points/count"),
            json={"filter": {"must": [{"key": key, "match": {"value": value}}]}, "exact": True},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result", {}).get("count", 0)
    except Exception:
        return -1


# ══════════════════════════════════════════════════════════════════
# TEST 6 — FULL E2E (Upload → Inspect → Retrieve)
# ══════════════════════════════════════════════════════════════════

def test_e2e_via_generate(buku_id: Optional[str] = None):
    """Test end-to-end: kirim request /konten/generate dengan buku_id."""
    _sep("TEST: E2E via /konten/generate")

    if buku_id is None:
        # Ambil buku_id yang ada
        buku_ids = _get_unique_buku_ids(DEBUG_COLLECTION)
        if not buku_ids:
            # Coba juga dari collection pipeline
            pipeline_col = os.getenv("QDRANT_PIPELINE_EKSTRACTION", "testPipeline")
            buku_ids = _get_unique_buku_ids(pipeline_col)
            if buku_ids:
                info(f"Menggunakan buku_id dari collection '{pipeline_col}'")

        if buku_ids:
            buku_id = buku_ids[0]
        else:
            warn("Tidak ada buku_id ditemukan — skip test generate")
            info("Upload PDF dulu via --test upload")
            return False

    info(f"buku_id: {buku_id}")
    info(f"Mengirim request /konten/generate dengan buku_id...")

    body = {
        "mapel_id":     "17",
        "elemen_id":    "debug_test",
        "elemen_label": "Debug Test",
        "materi":       "sistem somatosensory",
        "materi_id":    "debug__somatosensory",
        "kelas_id":     "12",
        "jenjang":      "12",
        "atp":          ["Debug test retrieval dengan buku_id"],
        "tipe":         "flashcard",
        "level":        "Mid",
        "buku_id":      buku_id,
    }

    try:
        r = requests.post(
            f"{API_BASE_URL}/konten/generate",
            json=body,
            headers=_api_headers(),
            timeout=120,
        )
        if r.status_code == 200:
            ok("Generate berhasil!")
            result = r.json()
            # Print summary
            if isinstance(result, dict):
                info(f"Keys: {list(result.keys())}")
                if "source" in result:
                    info(f"Source: {result.get('source')}")
            dim("(Response terlalu besar untuk ditampilkan penuh)")
            return True
        else:
            err(f"Generate gagal HTTP {r.status_code}")
            dim(r.text[:500])
            return False
    except requests.exceptions.Timeout:
        err("Timeout setelah 120s — LLM mungkin lambat")
        return False
    except Exception as e:
        err(f"Generate error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
# TEST 7 — CLEANUP
# ══════════════════════════════════════════════════════════════════

def test_cleanup(collection: Optional[str] = None):
    _sep("TEST: CLEANUP DEBUG COLLECTION")

    col = collection or DEBUG_COLLECTION
    info(f"Collection: {col}")

    # Safety check: jangan hapus collection utama
    if col == MAIN_COLLECTION:
        err(f"TIDAK BISA menghapus collection utama '{MAIN_COLLECTION}'!")
        return False

    try:
        r = requests.delete(_qdrant_url(f"/collections/{col}"), timeout=10)
        if r.status_code == 200:
            ok(f"Collection '{col}' dihapus")
        elif r.status_code == 404:
            warn(f"Collection '{col}' tidak ditemukan (sudah dihapus?)")
        else:
            err(f"Cleanup gagal HTTP {r.status_code}: {r.text}")
    except Exception as e:
        err(f"Cleanup error: {e}")

    return True


# ══════════════════════════════════════════════════════════════════
# RINGKASAN KONFIGURASI
# ══════════════════════════════════════════════════════════════════

def print_config():
    _sep("KONFIGURASI DEBUG", "█")
    info(f"API Base URL     : {API_BASE_URL}")
    info(f"API Key          : {'✓ (set)' if API_KEY else '✗ (tidak set)'}")
    info(f"Qdrant           : {_qdrant_host}:{QDRANT_PORT}")
    info(f"Main Collection  : {MAIN_COLLECTION}  ← TIDAK DISENTUH")
    info(f"Debug Collection : {DEBUG_COLLECTION}  ← Digunakan untuk testing")
    _sep("", "█")


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Debug Pipeline & Retriever System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Tests tersedia:
  health     Cek koneksi API + Qdrant
  upload     Upload PDF dan jalankan pipeline (ke debug collection)
  payload    Inspect payload points di Qdrant
  retrieve   Test dense search ke debug collection
  filter     Bandingkan filter buku_id vs source_file
  generate   Test E2E via /konten/generate dengan buku_id
  cleanup    Hapus debug collection
  all        Jalankan semua test (default)
        """,
    )
    parser.add_argument("--test", type=str, default="all",
                        help="Test yang akan dijalankan")
    parser.add_argument("--pdf", type=str, default=None,
                        help="Path ke file PDF untuk test upload")
    parser.add_argument("--buku-id", type=str, default=None,
                        help="buku_id spesifik untuk test")
    parser.add_argument("--collection", type=str, default=None,
                        help=f"Override debug collection (default: {DEBUG_COLLECTION})")
    parser.add_argument("--query", type=str, default="sistem saraf somatosensory",
                        help="Query untuk test retrieval")

    args = parser.parse_args()

    col = args.collection or DEBUG_COLLECTION

    print_config()

    tests = args.test.lower().split(",")

    for test_name in tests:
        test_name = test_name.strip()

        if test_name in ("all", "health"):
            if not test_health():
                if test_name == "all":
                    err("Health check gagal — berhenti")
                    sys.exit(1)

        if test_name in ("all", "upload"):
            # Upload hanya dijalankan jika ada --pdf atau ada PDF di uploads/
            test_upload(pdf_path=args.pdf, buku_id=args.buku_id)

        if test_name in ("all", "payload"):
            test_inspect_payload(collection=col, buku_id=args.buku_id)

        if test_name in ("all", "retrieve"):
            test_retrieve(collection=col, query=args.query)

        if test_name in ("all", "filter"):
            test_filter_comparison(collection=col)

        if test_name == "generate":
            test_e2e_via_generate(buku_id=args.buku_id)

        if test_name == "cleanup":
            test_cleanup(collection=col)

    _sep("SELESAI", "█")


if __name__ == "__main__":
    main()
