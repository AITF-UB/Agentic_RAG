# -*- coding: utf-8 -*-
"""
celery_app.py
=============
Konfigurasi Celery dengan Redis sebagai broker dan result backend.

Cara jalankan worker (dari direktori agentic_api/):
    celery -A celery_app worker --loglevel=info --concurrency=2 -Q pipeline

Monitoring (Flower):
    celery -A celery_app flower --port=5555
"""

from __future__ import annotations

import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "agentic_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.pipeline_task", "tasks.generate_task"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Result expiry: 7 hari
    result_expires=60 * 60 * 24 * 7,

    # Reliability: ack setelah task selesai (bukan saat diterima)
    # Jika worker crash di tengah task, task akan di-re-queue otomatis
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Pipeline berat — satu task per worker agar tidak OOM
    worker_prefetch_multiplier=1,

    # Tracking
    task_track_started=True,

    # Timeout: pipeline PDF & generasi soal AI max 15 menit
    task_soft_time_limit=3600,        # Soft: raise SoftTimeLimitExceeded setelah 50 menit
    task_time_limit=3900,            # Hard: kill worker setelah ~1,5jam menit

    # Reliability Broker: pemulihan cepat insiden server mati (> 1,5jam)
    broker_transport_options={"visibility_timeout": 4800}, # 4000 detik (> task_time_limit)

    # Routing: pipeline task masuk ke queue 'pipeline'
    task_routes={
        "tasks.pipeline_task.run_pipeline": {"queue": "pipeline"},
    },
)
