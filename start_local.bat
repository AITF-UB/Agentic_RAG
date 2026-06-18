@echo off
echo =======================================================
echo Menjalankan Agentic RAG secara Lokal (Tanpa Docker Desktop VM)
echo =======================================================
echo.

echo 1. Memastikan container Redis berjalan (sangat ringan ^< 50MB RAM)...
docker rm -f redis_broker_local 2>nul
docker run -d --name redis_broker_local -p 6379:6379 redis:7-alpine

echo.
echo 2. Membuka 2 terminal baru untuk Agentic API dan Celery...
echo Pastikan Anda sudah menjalankan: 'uv sync' di environment Python Anda.
echo.

:: Terminal 2: Agentic API (Port 8002)
start "Agentic API (Port 8002)" cmd /k "cd agentic_api && ..\.venv\Scripts\activate && title Agentic API (Port 8002) && echo Menjalankan Agentic API... && dotenv -f ..\.env run -- uvicorn main:app --port 8002"

:: Terminal 3: Celery Worker
:: Catatan: Di Windows, Celery direkomendasikan memakai --pool=solo
start "Celery Worker" cmd /k "cd agentic_api && ..\.venv\Scripts\activate && title Celery Worker && echo Menjalankan Celery Worker... && dotenv -f ..\.env run -- celery -A celery_app worker --loglevel=info --pool=solo"

echo Selesai! Anda akan melihat 2 jendela command prompt terbuka.
echo Anda bisa melakukan testing menggunakan VSCode REST Client seperti biasa.
pause
