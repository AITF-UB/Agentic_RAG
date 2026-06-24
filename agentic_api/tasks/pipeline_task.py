# -*- coding: utf-8 -*-
"""
tasks/pipeline_task.py
======================
Celery task untuk menjalankan pipeline PDF → Qdrant.

Task ini menggantikan _run_pipeline_task() di main.py yang sebelumnya
berjalan sebagai FastAPI BackgroundTask (in-process, volatile).

Dengan Celery:
  - Task persisten di Redis → tidak hilang saat API restart
  - Berjalan di worker process terpisah → tidak block event loop FastAPI
  - Auto-retry jika gagal (max 2x dengan 60s delay)
  - Progress bisa di-track via Celery result backend
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from datetime import datetime

# Tambahkan parent dir ke sys.path agar bisa import dari agentic_api/
_THIS_DIR = Path(__file__).resolve().parent.parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery_app import celery_app

from dotenv import load_dotenv
load_dotenv()


# ── Import pipeline (opsional — tidak crash jika tidak tersedia) ─────────────
try:
    from full_pipeline import (
        PipelineConfig, run_full_pipeline,
        DEFAULT_VLM_MODEL, DEFAULT_VLM_HOST,
        DEFAULT_DENSE_MODEL, DEFAULT_SPARSE_MODEL,
    )
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    DEFAULT_VLM_MODEL   = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")
    DEFAULT_VLM_HOST    = os.getenv("OLLAMA_HOST", "https://tipoff-errant-chatroom.ngrok-free.dev")
    DEFAULT_DENSE_MODEL  = os.getenv("DENSE_MODEL", "BAAI/bge-m3")
    DEFAULT_SPARSE_MODEL = os.getenv("SPARSE_MODEL", "naver/splade-cocondenser-ensembledistil")


OUTPUT_DIR = Path(os.getenv("PIPELINE_OUTPUT_DIR", "pipeline_output"))
CHUNKS_DIR = Path(os.getenv("PIPELINE_CHUNKS_DIR", "chunks"))


# ── Helper: normalisasi source_file ─────────────────────────────────────────
def _normalize_source_file(stem: str) -> str:
    normalized = stem.lower()
    for sfx in ("_chunks", "_final_paginated", "_structure"):
        if normalized.endswith(sfx):
            normalized = normalized[: -len(sfx)]
    return normalized


# ── Celery Task ──────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.pipeline_task.run_pipeline",
    max_retries=2,
    default_retry_delay=60,   # 60 detik sebelum retry
    acks_late=True,
    queue="pipeline",
)
def run_pipeline(self: Task, job_params: dict) -> dict:
    """
    Menjalankan full pipeline PDF → Qdrant.

    Args:
        job_params: dict berisi semua parameter PipelineParams + 'pdf_path'

    Returns:
        dict hasil pipeline (disimpan di Celery result backend / Redis)

    Raises:
        Exception: jika pipeline gagal dan max_retries tercapai
    """
    if not PIPELINE_AVAILABLE:
        raise RuntimeError(
            "full_pipeline.py tidak ditemukan. "
            "Pastikan file ada di direktori agentic_api/."
        )

    pdf_path = Path(job_params["pdf_path"])
    step = job_params.get("step")

    # Update state ke STARTED dengan progress info
    self.update_state(
        state="STARTED",
        meta={
            "message":  "Pipeline dimulai...",
            "filename": pdf_path.name,
            "step":     step or "all",
            "started_at": datetime.now().isoformat(),
        },
    )

    try:
        cfg = PipelineConfig(
            input_pdf         = pdf_path,
            output_base       = OUTPUT_DIR,
            outputs_root      = OUTPUT_DIR / "outputs",
            qdrant_host       = job_params.get("qdrant_host", os.getenv("QDRANT_HOST", "76.13.195.1")),
            qdrant_port       = int(job_params.get("qdrant_port", os.getenv("QDRANT_PORT", "6333"))),
            collection_name   = job_params.get("collection_name", os.getenv("QDRANT_PIPELINE_EKSTRACTION", "testPipeline")),
            chunk_size        = job_params.get("chunk_size", 1000),
            force_reindex     = job_params.get("force_reindex", False),
            start_page        = job_params.get("start_page", 0),
            end_page          = job_params.get("end_page", 0),
            mata_pelajaran    = job_params.get("mata_pelajaran"),
            id_kelas          = job_params.get("id_kelas"),
            jenjang           = job_params.get("jenjang"),
            id_guru           = job_params.get("id_guru"),
            buku_id           = job_params.get("buku_id"),
            vlm_model_id      = job_params.get("vlm_model", DEFAULT_VLM_MODEL),
            ollama_host       = job_params.get("ollama_host", DEFAULT_VLM_HOST),
            dense_model_name  = job_params.get("dense_model", DEFAULT_DENSE_MODEL),
            sparse_model_name = job_params.get("sparse_model", DEFAULT_SPARSE_MODEL),
            skip_existing     = False,
        )

        # Update progress sebelum jalankan step berat
        self.update_state(
            state="PROGRESS",
            meta={
                "message":  f"Menjalankan step: {step or 'all'}...",
                "filename": pdf_path.name,
                "step":     step or "all",
            },
        )

        run_full_pipeline(cfg, step=step if step else None)

        # Hitung artefak yang dihasilkan
        json_files  = list(OUTPUT_DIR.rglob("*_structure.json"))
        md_files    = list(OUTPUT_DIR.rglob("*_FINAL_PAGINATED.md"))
        jsonl_files = list(cfg.chunks_dir.glob("*.jsonl"))
        total_chunks = sum(
            sum(1 for line in open(f, encoding="utf-8") if line.strip())
            for f in jsonl_files
        )

        result = {
            "pdf_file":          pdf_path.name,
            "buku_id":           job_params.get("buku_id"),
            "source_file":       _normalize_source_file(pdf_path.stem),
            "step_run":          step or "all",
            "json_files":        [str(p) for p in json_files],
            "markdown_files":    [str(p) for p in md_files],
            "jsonl_files":       [str(p) for p in jsonl_files],
            "total_chunks":      total_chunks,
            "qdrant_collection": cfg.collection_name,
            "finished_at":       datetime.now().isoformat(),
        }
        return result

    except SoftTimeLimitExceeded:
        # Pipeline melebihi batas waktu 1 jam
        raise RuntimeError(
            f"Pipeline timeout setelah 1 jam. "
            f"Coba jalankan per-step (extract/describe/chunk/ingest) secara terpisah."
        )
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            # Retry otomatis (max 2x)
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            # Semua retry habis — biarkan task FAILURE
            raise RuntimeError(
                f"{type(exc).__name__}: {exc}\n\nTraceback:\n{tb}"
            ) from exc
