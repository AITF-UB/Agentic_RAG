FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create and set working directory
WORKDIR /app

# Install system dependencies in a single layer
# - build-essential: for compiling C-extensions (numpy, torch, etc.)
# - tesseract-ocr: for Docling OCR
# - libgl1, libglib2.0-0, etc.: for OpenCV/image processing
# - git: needed by some pip packages (e.g., docling submodules)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    libx11-xcb1 \
    libxrender1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxdamage1 \
    libxrandr2 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker cache layer — rebuild hanya jika requirements berubah)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Buat direktori yang dibutuhkan pipeline
RUN mkdir -p uploads pipeline_output chunks extraction outputs/extracted outputs/chunks

# Expose port untuk unified service
EXPOSE 8002

# 2 worker karena tim 6 sudah memperbolehkan (tapi perhatikan konsumsi memori model ML)
# Timeout 600s untuk pipeline yang prosesnya lama
CMD ["gunicorn", "main:app", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8002", "--timeout", "600"]
