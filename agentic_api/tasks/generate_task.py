# -*- coding: utf-8 -*-
"""
tasks/generate_task.py
======================
Celery task untuk menjalankan proses generasi konten (LangGraph) secara background.
Ini memungkinkan API menahan ratusan request bersamaan tanpa blocking/timeout.
"""

from __future__ import annotations
import asyncio
from celery import shared_task
import traceback

# Import graph
from graph import beta_graph

@shared_task(bind=True, name="tasks.generate_task.run_generation")
def run_generation(self, initial_state: dict):
    """
    Menjalankan LangGraph secara sinkron (membungkus asyncio).
    """
    print(f"[generate_task] Started generation for tipe: {initial_state.get('tipe')}")
    
    try:
        # Menjalankan event loop asyncio secara sinkron karena Celery worker default adalah proses sinkron
        # Pastikan tidak ada event loop lain yang aktif di thread yang sama
        final_state = asyncio.run(beta_graph.ainvoke(initial_state))
        
        final_payload = final_state.get("final_payload", {})
        
        # Kembalikan payload JSON
        print(f"[generate_task] Success for tipe: {initial_state.get('tipe')}")
        return final_payload
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        print(f"[generate_task] FAILED: {error_msg}")
        raise Exception(error_msg)
