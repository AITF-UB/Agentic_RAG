# -*- coding: utf-8 -*-
"""
tasks/generate_task.py
======================
Celery task untuk menjalankan proses generasi konten (LangGraph) secara background.
Ini memungkinkan API menahan ratusan request bersamaan tanpa blocking/timeout.
"""

from __future__ import annotations
import asyncio
import os
from dotenv import load_dotenv
from celery import shared_task
import traceback

# Wajib load .env di sini — Celery worker berjalan di proses TERPISAH dari Uvicorn.
# Tanpa ini, LANGCHAIN_TRACING_V2 dan LANGCHAIN_API_KEY tidak akan terbaca,
# sehingga LangSmith tidak bisa mencatat trace dari task yang berjalan di Celery.
load_dotenv()

# ── LangSmith tracing — wajib di-set di sini karena Celery adalah proses
# terpisah yang tidak mewarisi setting dari main.py (Uvicorn).
# Tanpa ini, semua trace dari Celery masuk ke project "default".
import os
_ls_project = os.getenv("LANGSMITH_PROJECT", "agentic-workflow")
os.environ["LANGSMITH_PROJECT"]  = _ls_project
os.environ["LANGSMITH_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
print(f"[generate_task] LangSmith project: {_ls_project}")

# Import graph (setelah load_dotenv agar env sudah tersedia)
from graph import beta_graph

def run_async_safely(coro):
    """
    Menjalankan coroutine asinkron dengan aman di lingkungan Celery worker.
    Jika event loop belum ada/belum aktif, gunakan loop.run_until_complete agar loop
    dapat digunakan kembali (reusable) dan menjaga connection pooling tetap hidup.
    Jika event loop sudah aktif di thread ini, jalankan di thread executor terpisah.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


@shared_task(
    bind=True,
    name="tasks.generate_task.run_generation",
    max_retries=2,
    default_retry_delay=30,
)
def run_generation(self, initial_state: dict):
    """
    Menjalankan LangGraph secara sinkron (membungkus asyncio).
    Mendukung murni auto-retry Celery jika koneksi LLM gagal/timeout.
    """
    print(f"[generate_task] Started generation for tipe: {initial_state.get('tipe')}")
    
    try:
        # Menjalankan event loop asyncio secara aman menggunakan helper reusable loop
        final_state = run_async_safely(beta_graph.ainvoke(initial_state))
        
        final_payload = final_state.get("final_payload", {})
        
        # Kembalikan payload JSON
        print(f"[generate_task] Success for tipe: {initial_state.get('tipe')}")
        return final_payload
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        print(f"[generate_task] FAILED (triggering Celery retry): {error_msg}")
        try:
            raise self.retry(exc=e, countdown=30)
        except self.MaxRetriesExceededError:
            raise Exception(error_msg)
