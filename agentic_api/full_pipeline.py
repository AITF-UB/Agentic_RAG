# -*- coding: utf-8 -*-
"""
execution/full_pipeline.py
===========================
Pipeline RAG utuh: PDF → Ekstraksi → Multimodal → Chunking → Qdrant

Menggabungkan 4 file terpisah:
  1. step1_extract_docling.py       → Ekstraksi Docling (teks + gambar)
  2. step2_describe_images-part2.py → Deskripsi gambar (VLM Qwen2.5-VL)
  3. chunker_base64_fixed.ipynb     → Chunking + cleaning + page range filter
  4. hybrid_ingest_adjusted_chunk4  → Ingest hybrid ke Qdrant (BGE-M3 + SPLADE)

Struktur output terpusat (default: outputs/):
  outputs/
    extracted/          ← hasil Step 1: JSON struktur + gambar per buku
      <pdf_name>/
        <pdf_name>_structure.json
        <pdf_name>_FINAL_PAGINATED.md
        extracted_assets/
          *.png
    chunks/             ← hasil Step 3: JSONL siap ingest ke Qdrant
      <pdf_name>_FINAL_PAGINATED_chunks.jsonl

Cara pakai:
  # Jalankan semua step
  python execution/full_pipeline.py --input-folder "Kelas 10"

  # Jalankan step tertentu
  python execution/full_pipeline.py --step extract
  python execution/full_pipeline.py --step describe
  python execution/full_pipeline.py --step chunk
  python execution/full_pipeline.py --step ingest

  # Custom output root
  python execution/full_pipeline.py --outputs-root my_outputs

  # Custom config
  python execution/full_pipeline.py --qdrant-host 76.13.195.1 --collection hybrid_v2
"""

from __future__ import annotations

import argparse
import base64
import gc
import hashlib
import json
import os
import re
import shutil
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURASI TERPUSAT
# ══════════════════════════════════════════════════════════════════════════════

def _env_str(name: str, default: str) -> str:
    val = os.getenv(name)
    return val if val else default


# ── Default shared antar file ─────────────────────────────────────────────
DEFAULT_VLM_MODEL  = _env_str("VLM_MODEL", "ub-sr-all")
DEFAULT_VLM_HOST   = _env_str("VLM_HOST", "https://providers-else-hear-wheel.trycloudflare.com")
DEFAULT_DENSE_MODEL  = _env_str("DENSE_MODEL", "BAAI/bge-m3")
DEFAULT_SPARSE_MODEL = _env_str("SPARSE_MODEL", "naver/splade-cocondenser-ensembledistil")


@dataclass
class PipelineConfig:
    """Semua konfigurasi pipeline di satu tempat."""

    # ── Path ──────────────────────────────────────────────────────────────────
    # Gunakan input_pdf untuk memproses SATU file PDF langsung.
    # Jika input_pdf diset, input_folder diabaikan oleh Step 1.
    input_pdf:       Optional[Path] = None  # Path ke satu file PDF
    input_folder:    Path = field(default_factory=lambda: Path("Kelas 10"))
    done_folder:     Path = field(default_factory=lambda: Path("BukuSIBI_done"))
    failed_folder:   Path = field(default_factory=lambda: Path("BukuSIBI_failed"))
    output_base:     Path = field(default_factory=lambda: Path("."))
    config_file:     Optional[Path] = None  # Halaman_materi_buku.txt

    # ── Output terpusat ───────────────────────────────────────────────────────
    # Semua artefak pipeline dikumpulkan di bawah satu root:
    #   outputs/
    #     extracted/   ← hasil Step 1 (JSON + gambar)
    #     chunks/      ← hasil Step 3 (JSONL)
    outputs_root:    Path = field(default_factory=lambda: Path("outputs"))

    @property
    def extracted_dir(self) -> Path:
        """Folder terpusat untuk hasil ekstraksi Docling (Step 1)."""
        return self.outputs_root / "extracted"

    @property
    def chunks_dir(self) -> Path:
        """Folder terpusat untuk hasil chunking (Step 3)."""
        return self.outputs_root / "chunks"

    # ── Model ─────────────────────────────────────────────────────────────────
    # VLM diakses melalui OpenAI-compatible API (Ollama, llama.cpp, vLLM, dll.)
    # Request body menggunakan OpenAI chat completion template.
    vlm_model_id:       str = _env_str("VLM_MODEL", "ub-sr-all")
    ollama_host:        str = DEFAULT_VLM_HOST  # Base URL server VLM
    dense_model_name:   str = _env_str("DENSE_MODEL", "BAAI/bge-m3")
    sparse_model_name:  str = _env_str("SPARSE_MODEL", "naver/splade-cocondenser-ensembledistil")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host:      str  = _env_str("QDRANT_HOST", "76.13.195.1")
    qdrant_port:      int  = int(_env_str("QDRANT_PORT", "6333"))
    collection_name:  str  = _env_str("QDRANT_PIPELINE_EKSTRACTION", "test_pipeline")
    qdrant_timeout:   int  = 120
    force_reindex:    bool = False
    batch_size:       int  = 32

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size:      int = 1000
    min_chunk_size:  int = 150
    file_pattern:    str = "**/*FINAL_PAGINATED.md"

    # ── Page range untuk ekstraksi (Step 1) ───────────────────────────────────
    # Jika start_page == 0 dan end_page == 0  →  proses SEMUA halaman
    # Jika start_page > 0 atau end_page > 0   →  potong PDF ke range tersebut
    start_page:      int  = 0   # 0 = tidak dibatasi (dari halaman pertama)
    end_page:        int  = 0   # 0 = tidak dibatasi (sampai halaman terakhir)

    # ── Metadata buku (untuk chunk) ────────────────────────────────────────
    # Digunakan sebagai nilai langsung (atau fallback jika tidak ada di config file)
    mata_pelajaran:  Optional[str] = None  # mis. "Biologi", "Matematika"
    id_kelas:        Optional[str] = None  # ID_Kelas
    jenjang:         Optional[str] = None  # Jenjang Kelas (mis. X, XI, XII)
    id_guru:         Optional[str] = None  # ID Guru
    buku_id:         Optional[str] = None  # ID unik buku, di-assign di upload API
    skip_existing:   bool = True

    def ensure_dirs(self) -> None:
        """Pastikan semua folder pipeline ada."""
        # Jika mode single-PDF, folder input tidak perlu dibuat
        if self.input_pdf is None:
            os.makedirs(self.input_folder, exist_ok=True)
        os.makedirs(self.done_folder, exist_ok=True)
        os.makedirs(self.failed_folder, exist_ok=True)
        # folder output terpusat
        os.makedirs(self.extracted_dir, exist_ok=True)
        os.makedirs(self.chunks_dir, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — EKSTRAKSI DOCLING
# ══════════════════════════════════════════════════════════════════════════════

def step1_extract(config: PipelineConfig) -> List[Path]:
    """
    Baca PDF input (satu file via config.input_pdf, atau semua PDF di
    config.input_folder), ekstrak teks + gambar menggunakan Docling,
    simpan struktur ke file JSON. Tidak butuh GPU.

    Hasil disimpan terpusat di:
      outputs/extracted/<pdf_name>/
        ├── <pdf_name>_structure.json
        └── extracted_assets/
              └── *.png

    Returns: list path JSON yang dihasilkan.
    """
    from pypdf import PdfReader, PdfWriter
    from model_registry import get_docling_converter

    config.ensure_dirs()

    print("=" * 60)
    print("  STEP 1 — Ekstraksi Docling")
    print("=" * 60)

    # ── Tentukan daftar PDF yang akan diproses ────────────────────────────────
    if config.input_pdf is not None:
        # Mode single-PDF: hanya proses satu file
        single_pdf = Path(config.input_pdf)
        if not single_pdf.exists():
            print(f"\n❌  File PDF tidak ditemukan: {single_pdf}")
            return []
        if not single_pdf.suffix.lower() == ".pdf":
            print(f"\n❌  File bukan PDF: {single_pdf}")
            return []
        pdf_files = [single_pdf]
        print(f"  Input     : {single_pdf}")
    else:
        # Mode folder: proses semua PDF di input_folder
        pdf_files = sorted(config.input_folder.glob("*.pdf"))
        print(f"  Input     : {config.input_folder}/")

    print(f"  Output    : {config.extracted_dir}/")
    print(f"  Selesai   : {config.done_folder}/")
    print(f"  Gagal     : {config.failed_folder}/")
    print("=" * 60)

    if not pdf_files:
        print("\n⚠️  Tidak ada file PDF untuk diproses.")
        return []

    print(f"\n📚 Ditemukan {len(pdf_files)} file PDF.\n")

    json_paths: List[Path] = []

    for original_pdf in pdf_files:
        pdf_name   = original_pdf.stem
        # ── Simpan di folder terpusat: outputs/extracted/<pdf_name>/ ──────────
        output_dir = config.extracted_dir / pdf_name
        image_dir  = output_dir / "extracted_assets"
        json_path  = output_dir / f"{pdf_name}_structure.json"

        # Skip jika sudah pernah diproses
        if config.skip_existing and json_path.exists():
            print(f"⏭️  [{pdf_name}] Sudah diproses sebelumnya, dilewati.\n")
            json_paths.append(json_path)
            continue

        print(f"📄 [{pdf_name}] Mulai ekstraksi...")
        os.makedirs(image_dir, exist_ok=True)
        start_time = datetime.now()

        try:
            working_pdf = original_pdf

            # ── Potong PDF jika ada page range ───────────────────────────────
            # Aturan: start_page==0 DAN end_page==0  → semua halaman
            #         selain itu                     → potong ke range yang diminta
            use_page_range = config.start_page > 0 or config.end_page > 0
            if use_page_range:
                reader = PdfReader(original_pdf)
                total_doc_pages = len(reader.pages)
                # Konversi ke indeks 0-based; 0 di config berarti batas dokumen
                s = max(0, config.start_page - 1) if config.start_page > 0 else 0
                e = min(total_doc_pages, config.end_page)  if config.end_page  > 0 else total_doc_pages
                if s >= e:
                    print(f"   ⚠️  Range halaman {config.start_page}–{config.end_page} tidak valid "
                          f"(dokumen punya {total_doc_pages} hal). Proses semua halaman.")
                    use_page_range = False
                else:
                    writer = PdfWriter()
                    for i in range(s, e):
                        writer.add_page(reader.pages[i])
                    sliced_pdf = Path(f"_sliced_{pdf_name}.pdf")
                    with open(sliced_pdf, "wb") as f:
                        writer.write(f)
                    working_pdf = sliced_pdf
                    print(f"   ✂️  Menggunakan halaman {s+1}–{e} dari {total_doc_pages} ({e-s} hal)")

            api_url = os.getenv("MODEL_API_URL")
            if api_url:
                import requests
                import base64
                print(f"   🌐 Mengirim PDF ke API: {api_url}/extract/docling ...")
                with open(working_pdf, "rb") as f:
                    resp = requests.post(f"{api_url}/extract/docling", files={"file": f}, timeout=600)
                resp.raise_for_status()
                data = resp.json()
                total_pages = data.get("total_pages", "?")
                elements_raw = data.get("elements", [])
                
                print(f"   ✅ Selesai (via API). Total halaman: {total_pages}")
                
                elements = []
                img_counter = 0
                for el in elements_raw:
                    if "image_base64" in el:
                        img_counter += 1
                        page_no = el["page"]
                        img_filename = f"{el['type']}_p{page_no:03d}_{img_counter:03d}.png"
                        img_path = image_dir / img_filename
                        
                        img_data = base64.b64decode(el["image_base64"])
                        with open(img_path, "wb") as f:
                            f.write(img_data)
                            
                        elements.append({
                            "type": el["type"],
                            "page": page_no,
                            "img_path": str(img_path),
                            "img_rel": f"extracted_assets/{img_filename}",
                            "description": None,
                        })
                        print(f"   🖼️  Simpan gambar dari API: {img_filename}")
                    else:
                        elements.append(el)
            else:
                # --- Docling (singleton dari registry) ---
                converter = get_docling_converter()

                print(f"   🔍 Mengekstrak struktur PDF (lokal)...")
                result      = converter.convert(working_pdf)
                total_pages = len(result.document.pages) if hasattr(result.document, "pages") else "?"
                print(f"   ✅ Selesai. Total halaman: {total_pages}")

                # --- Kumpulkan elemen ---
                elements    = []
                img_counter = 0
                current_page = 0

                for element, _ in result.document.iterate_items():
                    page_no = element.prov[0].page_no if element.prov else current_page
                    current_page = page_no

                    if element.label == "section_header":
                        elements.append({
                            "type": "section_header",
                            "page": page_no,
                            "text": element.text,
                        })
                    elif element.label in ("text", "list_item"):
                        text = element.text.strip()
                        if text:
                            elements.append({
                                "type":  element.label,
                                "page":  page_no,
                                "text":  text,
                            })
                    elif element.label == "formula":
                        elements.append({
                            "type": "formula",
                            "page": page_no,
                            "text": element.text,
                        })
                    elif element.label in ("picture", "table"):
                        if hasattr(element, "image") and element.image is not None:
                            try:
                                pil_img = element.image.pil_image
                                if pil_img.width < 80 or pil_img.height < 80:
                                    continue
                                img_counter += 1
                                img_filename = f"{element.label}_p{page_no:03d}_{img_counter:03d}.png"
                                img_path     = image_dir / img_filename
                                pil_img.save(img_path)
                                elements.append({
                                    "type":        element.label,
                                    "page":        page_no,
                                    "img_path":    str(img_path),
                                    "img_rel":     f"extracted_assets/{img_filename}",
                                    "description": None,
                                })
                                print(f"   🖼️  Simpan gambar: {img_filename}")
                            except Exception as e_img:
                                print(f"   ⚠️  Gagal simpan gambar halaman {page_no}: {e_img}")

            # --- Simpan JSON ---
            structure = {
                "pdf_name":     pdf_name,
                "total_pages":  total_pages,
                "extracted_at": datetime.now().isoformat(),
                "elements":     elements,
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(structure, f, ensure_ascii=False, indent=2)

            elapsed = (datetime.now() - start_time).seconds
            print(f"   💾 Struktur disimpan: {json_path}")
            print(f"   📊 {img_counter} gambar diekstrak — {elapsed}s")

            # Pindahkan PDF hanya jika mode batch (folder), bukan mode single-PDF (API upload).
            # Pada mode API, file harus tetap di tempat agar re-run step lain tidak gagal.
            if config.input_pdf is None:
                shutil.move(str(original_pdf), str(config.done_folder / original_pdf.name))
                print(f"   📦 PDF dipindah ke: {config.done_folder}/\n")
            else:
                print(f"   ✅ Mode single-PDF: file tetap di tempat.\n")
            json_paths.append(json_path)

        except Exception as e:
            elapsed = (datetime.now() - start_time).seconds
            print(f"   ❌ GAGAL [{pdf_name}]: {e} ({elapsed}s)")
            if config.input_pdf is None:
                shutil.move(str(original_pdf), str(config.failed_folder / original_pdf.name))
                print(f"   📦 PDF dipindah ke: {config.failed_folder}/\n")
            else:
                print(f"   ❌ Mode single-PDF: file tetap di tempat.\n")

        finally:
            # Hapus file PDF sementara (hasil pemotongan) jika ada
            if use_page_range and "sliced_pdf" in locals() and Path(sliced_pdf).exists():
                os.remove(sliced_pdf)

    print("=" * 60)
    print(f"  STEP 1 selesai. {len(json_paths)} file berhasil diekstrak.")
    print("=" * 60)
    return json_paths


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — DESKRIPSI GAMBAR (VLM via Ollama)
# ══════════════════════════════════════════════════════════════════════════════

def step2_describe_images(config: PipelineConfig, json_paths: Optional[List[Path]] = None) -> List[Path]:
    """
    Proses setiap gambar dengan VLM melalui OpenAI-compatible API, rakit Markdown final.
    Request body menggunakan OpenAI chat completion template.

    Model default  : unsloth/Qwen3-VL-4B-Instruct-GGUF
    Server host    : config.ollama_host  (default: http://localhost:11434)

    Returns: list path Markdown final yang dihasilkan.
    """
    import base64
    import requests as _requests
    from PIL import Image
    import io

    vlm_url = config.ollama_host.rstrip("/") + "/v1/chat/completions"
    model_name = config.vlm_model_id

    print("=" * 60)
    print("  STEP 2 — Deskripsi VLM + Rakitan Markdown")
    print("=" * 60)
    print(f"  Server host : {config.ollama_host}")
    print(f"  Model       : {model_name}")
    print("=" * 60)

    # ── Cek koneksi ke server VLM ───────────────────────────────────────────
    # Header ini diperlukan saat diakses lewat ngrok (free tier)
    # agar ngrok tidak memblokir request dengan halaman browser challenge
    _NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}
    _vlm_ok = True
    try:
        ping = _requests.get(config.ollama_host.rstrip("/") + "/v1/models", timeout=10, headers=_NGROK_HEADERS)
        ping.raise_for_status()
        data = ping.json()
        if "data" in data:
            available_models = [m["id"] for m in data["data"]]
            print(f"\n✅ Terhubung ke server VLM. Model tersedia: {available_models}")
            if model_name not in available_models:
                print(f"   ⚠️  Model '{model_name}' tidak dalam daftar. Server mungkin tetap bisa menjalankannya.")
        else:
            print(f"\n✅ Terhubung ke server VLM di {config.ollama_host}")
    except _requests.exceptions.ConnectionError:
        print(f"\n❌  Tidak bisa terhubung ke server VLM di {config.ollama_host}")
        print("   Pastikan server sudah berjalan.\n")
        _vlm_ok = False
    except Exception as conn_err:
        print(f"\n⚠️  Peringatan — tidak bisa cek /v1/models: {conn_err}")
        print(f"   Pipeline tetap lanjut; jika gagal nanti periksa server VLM.\n")
    if not _vlm_ok:
        return []

    # ── Helper: encode gambar ke base64 ─────────────────────────────────────
    def validate_and_encode_image(img_path: str) -> Optional[str]:
        """Validasi gambar, resize jika perlu, kembalikan base64 string."""
        if not img_path or not Path(img_path).exists():
            return None
        try:
            pil_image = Image.open(img_path).convert("RGB")
        except Exception:
            return None
        if pil_image.width < 80 or pil_image.height < 80:
            return None
        MAX_DIM = 960
        if pil_image.width > MAX_DIM or pil_image.height > MAX_DIM:
            pil_image.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # ── Helper: prompt per jenis ─────────────────────────────────────────────
    def build_prompt(label: str) -> str:
        if label == "table":
            return (
                "Ini adalah gambar TABEL dari buku pelajaran. "
                "Jelaskan isi tabel ini dalam SATU PARAGRAF yang mengalir dan mudah dipahami. "
                "Sebutkan topik utama tabel, kolom-kolom yang ada, "
                "serta data atau pola penting yang terlihat. "
                "Jangan gunakan format tabel, bullet, atau numbering."
            )
        else:
            return (
                "Analisis gambar dari buku pelajaran ini. "
                "Pertama tentukan jenisnya: diagram, grafik, foto, ilustrasi, atau rumus. "
                "Kemudian deskripsikan:\n"
                "1. Apa yang ditampilkan secara keseluruhan\n"
                "2. Elemen-elemen utama dan relasinya\n"
                "3. Teks, angka, atau label penting yang terlihat\n"
                "4. Informasi kunci yang dapat diambil pembaca\n"
                "Deskripsikan gambar dari buku pelajaran ini dalam satu paragraf yang informatif."
            )

    # ── Helper: kirim gambar ke VLM dan dapatkan deskripsi ──────────────────
    def describe_image(img_path: str, label: str) -> Optional[str]:
        b64 = validate_and_encode_image(img_path)
        if b64 is None:
            return None
        prompt_text = build_prompt(label)
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": "Kamu adalah helpfull assistant untuk kebutuhan captioning gambar materi pendidikan. Langsung berikan caption gambar tanpa tambahan kata lainya yang tidak berkaitan dengan caption"
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            "max_tokens": 3000,
            "temperature": 0.7,
            "chat_template_kwargs": {
                "enable_thinking": False
            },
        }
        try:
            resp = _requests.post(vlm_url, json=payload, timeout=120, headers=_NGROK_HEADERS)
            resp.raise_for_status()
            result = resp.json()["choices"][0]["message"]["content"].strip()
            skip_kw = ["SKIP", "tidak dapat melihat", "belum memberikan",
                        "tidak dapat membantu", "maaf saya", "saya tidak bisa"]
            if any(kw.lower() in result.lower() for kw in skip_kw):
                return None
            return result if result else None
        except _requests.exceptions.Timeout:
            return f"⚠️ Gagal dianalisis: timeout setelah 120 detik."
        except _requests.exceptions.HTTPError as http_err:
            return f"⚠️ Gagal dianalisis: HTTP {http_err.response.status_code} — {http_err}"
        except Exception as e:
            return f"⚠️ Gagal dianalisis: {e}"

    # ── Helper: format blok visual ────────────────────────────────────────────
    def format_visual_block(label, img_rel, description):
        if label == "table":
            return (
                "\n---\n"
                "**📊 Tabel**\n\n"
                f"![Tabel]({img_rel})\n\n"
                f"{description}\n\n"
            )
        else:
            return (
                "\n---\n"
                "**🖼️ Gambar/Diagram**\n\n"
                f"![Visual]({img_rel})\n\n"
                f"> **Deskripsi Visual:** {description}\n\n"
            )

    # ── Cari JSON paths ────────────────────────────────────────────────────
    if json_paths is None:
        # Cari di folder terpusat terlebih dahulu
        extracted_root = config.extracted_dir
        json_paths = sorted(extracted_root.glob("*/*_structure.json"))

        # Fallback: cari pola lama output_multimodal_* di output_base
        if not json_paths:
            json_paths = []
            for d in config.output_base.iterdir():
                if d.is_dir() and d.name.startswith("output_multimodal_"):
                    json_paths += list(d.glob("*_structure.json"))
            json_paths = sorted(json_paths)

    if not json_paths:
        print("⚠️  Tidak ada file JSON hasil Step 1.")
        return []

    print(f"📂 Ditemukan {len(json_paths)} file untuk diproses.\n")

    md_paths: List[Path] = []

    for json_path in json_paths:
        pdf_name   = json_path.stem.replace("_structure", "")
        output_dir = json_path.parent          # outputs/extracted/<pdf_name>/
        final_md   = output_dir / f"{pdf_name}_FINAL_PAGINATED.md"

        if config.skip_existing and final_md.exists():
            print(f"⏭️  [{pdf_name}] Markdown final sudah ada, dilewati.\n")
            md_paths.append(final_md)
            continue

        print(f"{'='*55}")
        print(f"📝 [{pdf_name}]")
        print(f"{'='*55}")
        start_time = datetime.now()

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                structure = json.load(f)

            elements    = structure.get("elements", [])
            total_pages = structure.get("total_pages", "?")

            assembled_md  = f"# {pdf_name.replace('_', ' ')}\n\n"
            assembled_md += f"*Diekstrak: {datetime.now().strftime('%d %B %Y, %H:%M')}*\n\n"
            assembled_md += "---\n\n"

            current_page = 0
            visual_ok    = 0
            visual_skip  = 0
            visual_fail  = 0
            visual_total = sum(1 for el in elements if el["type"] in ("picture", "table"))
            visual_idx   = 0

            for el in elements:
                page_no = el.get("page", current_page)
                if page_no != current_page:
                    if current_page != 0:
                        assembled_md += "\n<br>\n"
                    assembled_md += f"\n\n---\n## 📄 Halaman {page_no}\n\n"
                    current_page = page_no

                t = el["type"]
                if t == "section_header":
                    assembled_md += f"\n### {el['text']}\n\n"
                elif t == "text":
                    assembled_md += f"{el['text']}\n\n"
                elif t == "list_item":
                    assembled_md += f"- {el['text']}\n"
                elif t == "formula":
                    assembled_md += f"\n`{el['text']}`\n\n"
                elif t in ("picture", "table"):
                    visual_idx += 1
                    img_path = el.get("img_path")
                    img_rel  = el.get("img_rel", "")

                    print(f"  🔍 [{visual_idx}/{visual_total}] {t} — hal. {page_no}...")
                    description = describe_image(img_path, t)

                    if description is None:
                        visual_skip += 1
                        print(f"      ↩️  Dilewati.")
                    elif description.startswith("⚠️"):
                        visual_fail += 1
                        assembled_md += format_visual_block(t, img_rel, description)
                        print(f"      ⚠️  Gagal: {description}")
                    else:
                        assembled_md += format_visual_block(t, img_rel, description)
                        visual_ok += 1
                        print(f"      ✅ Selesai.")

            elapsed = (datetime.now() - start_time).seconds
            # Statistik hanya di-print ke console, TIDAK ditulis ke markdown
            # agar tidak ikut masuk ke dalam chunks Qdrant

            with open(final_md, "w", encoding="utf-8") as f:
                f.write(assembled_md.strip())

            print(f"\n  ✅ SELESAI: {final_md}")
            print(f"  📊 {visual_ok} OK, {visual_skip} skip, {visual_fail} gagal — {elapsed//60}m {elapsed%60}s\n")
            md_paths.append(final_md)

        except Exception as e:
            print(f"\n  ❌ GAGAL [{pdf_name}]: {e}")
            traceback.print_exc()

    print("=" * 60)
    print(f"  STEP 2 selesai. {len(md_paths)} file Markdown dihasilkan.")
    print("=" * 60)
    return md_paths


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — CHUNKING + CLEANING
# ══════════════════════════════════════════════════════════════════════════════

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class _HdrState:
    last_struct_level: int = 0
    last_heading_level: int = 0


@dataclass
class HierarchyMetadata:
    """Metadata hierarchy untuk setiap chunk."""
    chapter:            Optional[str]              = None
    chapter_num:        Optional[int]              = None
    section:            Optional[str]              = None
    section_letter:     Optional[str]              = None
    subsection:         Optional[int]              = None
    subsubsection:      Optional[str]              = None
    page:               Optional[int]              = None
    current_header:     Optional[str]              = None
    header_level:       Optional[int]              = None
    has_visual_content: Union[bool, List[Dict[str, str]]] = False
    mata_pelajaran:     Optional[str]              = None
    id_kelas:           Optional[str]              = None
    jenjang:            Optional[str]              = None
    id_guru:            Optional[str]              = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if k == "has_visual_content":
                result[k] = v
            elif v is not None:
                result[k] = v
        return result


@dataclass
class ChunkWithMetadata:
    """Chunk dengan metadata hierarchy."""
    content:  str
    metadata: HierarchyMetadata


# ── Markdown Header Cleaner ──────────────────────────────────────────────────

class MarkdownHeaderCleaner:
    """Cleaner untuk menstandarkan hierarchy header Markdown."""

    HEADER_RE  = re.compile(r"^\s*(?:#sym:)?(?P<hashes>#{1,6})\s*(?P<title>[^\n\r]+?)\s*$")
    RE_CHAPTER = re.compile(r"^bab\s+\d+\b", re.IGNORECASE)
    RE_LETTER  = re.compile(r"^[A-Z]\.\s*\S")
    RE_DIGIT   = re.compile(r"^\d+\.\s*\S?")
    RE_LOWER   = re.compile(r"^[a-z]\.\s*\S")
    RE_PAGE    = re.compile(
        r"^(?:\[(?:HALAMAN|PAGE)[_\s-]*\d+\]"
        r"|📄\s*Halaman\s+\d+"
        r"|.*Halaman\s+\d+\s*$"
        r")",
        re.IGNORECASE,
    )
    RE_ALT = re.compile(r"^alternatif\s+penyelesaian\b", re.IGNORECASE)

    def __init__(self) -> None:
        self.state         = _HdrState()
        self.header_count  = 0
        self.changed_count = 0

    def _classify(self, title: str) -> str:
        t = title.strip()
        if self.RE_PAGE.match(t):    return "PAGE"
        if self.RE_CHAPTER.match(t): return "CHAPTER"
        if self.RE_LETTER.match(t):  return "LETTER"
        if self.RE_DIGIT.match(t):   return "DIGIT"
        if self.RE_LOWER.match(t):   return "LOWER"
        if self.RE_ALT.match(t):     return "ALT"
        return "OTHER"

    def _target_level(self, kind: str) -> Tuple[int, bool, bool]:
        if kind == "CHAPTER": return 1, True,  True
        if kind == "LETTER":  return 2, True,  True
        if kind == "DIGIT":   return 3, True,  True
        if kind == "LOWER":   return 4, True,  True
        if kind == "PAGE":    return 5, False, False
        if kind == "ALT":
            base  = self.state.last_heading_level or self.state.last_struct_level or 2
            level = min(max(base + 1, (self.state.last_struct_level or 2) + 1), 6)
            return level, False, True
        base_struct = self.state.last_struct_level or 2
        return min(base_struct + 1, 6), False, True

    def fix_markdown_headers(self, text: str) -> Tuple[str, int, int]:
        self.state         = _HdrState()
        self.header_count  = 0
        self.changed_count = 0
        out_lines: List[str] = []

        for line in text.splitlines(keepends=True):
            m = self.HEADER_RE.match(line)
            if not m:
                out_lines.append(line)
                continue

            self.header_count += 1
            title = m.group("title").rstrip()
            kind  = self._classify(title)
            target, upd_struct, upd_heading = self._target_level(kind)

            new_line = (
                f"{'#' * target} {title}\n"
                if line.endswith("\n")
                else f"{'#' * target} {title}"
            )
            if new_line != line:
                self.changed_count += 1
            out_lines.append(new_line)

            if upd_struct:
                self.state.last_struct_level = target
            if upd_heading:
                self.state.last_heading_level = target

        return "".join(out_lines), self.header_count, self.changed_count


# ── Chunk Content Cleaner ────────────────────────────────────────────────────

class ChunkContentCleaner:
    """Membersihkan noise dari page_content hasil chunk."""

    VISUAL_BLOCK_RE = re.compile(
        r"(?im)^\s*---\s*\n"
        r"\s*\*\*[^\n]*(?:🖼️|gambar|diagram|tabel|visual)[^\n]*\*\*\s*\n"
        r"(?:\s*>.*(?:\n|$))*"
        r"\s*(?:---\s*)?(?=\n|$)"
    )
    MARKDOWN_IMAGE_RE = re.compile(r"!\[.*?\]\(.*?\)")
    HTML_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
    HORIZONTAL_RULE_LINE_RE = re.compile(r"(?m)^\s*-{3,}\s*$")
    # Buang baris statistik pipeline (footer dari Step 2) agar tidak masuk ke chunks
    STATS_FOOTER_RE = re.compile(
        r"\*[📊🖼️]?\s*Statistik[^\n]*visual[^\n]*Durasi[^\n]*\*",
        re.IGNORECASE,
    )
    MULTISPACE_RE = re.compile(r"[ \t]{2,}")
    MANY_NEWLINES_RE = re.compile(r"\n{3,}")
    COVER_ISBN_RE = re.compile(r"\bISBN\b", re.IGNORECASE)
    COVER_MINISTRY_RE = re.compile(r"Kementerian", re.IGNORECASE)

    @classmethod
    def clean_text(cls, text: str) -> str:
        if not text:
            return ""
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = cls.STATS_FOOTER_RE.sub("", cleaned)       # ← buang footer statistik pipeline
        cleaned = cls.VISUAL_BLOCK_RE.sub("\n", cleaned)
        cleaned = cls.MARKDOWN_IMAGE_RE.sub("", cleaned)
        cleaned = cls.HTML_BR_RE.sub("\n", cleaned)
        cleaned = cls.HORIZONTAL_RULE_LINE_RE.sub("", cleaned)
        lines = []
        for line in cleaned.split("\n"):
            line = cls.MULTISPACE_RE.sub(" ", line).strip()
            lines.append(line)
        cleaned = "\n".join(lines)
        cleaned = cls.MANY_NEWLINES_RE.sub("\n\n", cleaned)
        cleaned = cleaned.strip(" \t\n-")
        return cleaned.strip()

    @classmethod
    def should_skip_chunk(cls, text: str) -> bool:
        cleaned = cls.clean_text(text)
        if not cleaned:
            return True
        if cls.COVER_ISBN_RE.search(cleaned) and cls.COVER_MINISTRY_RE.search(cleaned):
            return True
        compact = re.sub(r"[\s\-_.|:;]+", "", cleaned)
        if not compact:
            return True
        return False


# ── Hierarchy Aware Chunker ──────────────────────────────────────────────────

class HierarchyAwareChunker:
    """Chunker yang mempertahankan metadata hierarchy."""

    HEADER_RE = re.compile(r"^\s*(?P<hashes>#{1,6})\s*(?P<title>[^\n\r]+?)\s*$")

    PAGE_RE = re.compile(
        r"(?:\[(?:HALAMAN|PAGE)[_\s-]*(\d+)\]"
        r"|📄\s*Halaman\s+(\d+)"
        r")",
        re.IGNORECASE,
    )

    PAGE_TITLE_RE = re.compile(
        r"(?:.*Halaman\s+(\d+)\s*$"
        r"|\[(?:HALAMAN|PAGE)[_\s-]*(\d+)\]"
        r"|📄\s*Halaman\s+(\d+)"
        r")",
        re.IGNORECASE,
    )

    IMAGE_RE = re.compile(r"!\[.*?\]\((.*?)\)")

    def __init__(
        self,
        chunk_size:     int = 500,
        min_chunk_size: int = 150,
        mata_pelajaran: Optional[str] = None,
        id_kelas:       Optional[str] = None,
        jenjang:        Optional[str] = None,
        id_guru:        Optional[str] = None,
        extraction_dir: Optional[Path] = None,
    ) -> None:
        self.chunk_size      = chunk_size
        self.min_chunk_size  = min_chunk_size
        self.mata_pelajaran  = mata_pelajaran
        self.id_kelas        = id_kelas
        self.jenjang         = jenjang
        self.id_guru         = id_guru
        self.metadata        = HierarchyMetadata()
        self.content_cleaner = ChunkContentCleaner()
        self._img_prefix: str = ""
        self._extraction_dir = extraction_dir or Path(".")

    def _parse_header_title(self, title: str, level: int) -> None:
        t = title.strip()
        page_match = self.PAGE_TITLE_RE.match(t)
        if page_match:
            page_num = page_match.group(1) or page_match.group(2) or page_match.group(3)
            if page_num:
                self.metadata.page = int(page_num)
            return

        if level == 1:
            m = re.match(r"^bab\s+(\d+)\b", t, re.IGNORECASE)
            if m:
                self.metadata.chapter_num    = int(m.group(1))
                self.metadata.chapter        = t
                self.metadata.section        = None
                self.metadata.section_letter = None
                self.metadata.subsection     = None
                self.metadata.subsubsection  = None
        elif level == 2:
            m = re.match(r"^([A-Z])\.\s*(.*)", t)
            if m:
                self.metadata.section_letter = m.group(1)
                self.metadata.section        = t
                self.metadata.subsection     = None
                self.metadata.subsubsection  = None
        elif level == 3:
            m = re.match(r"^(\d+)\.\s*(.*)", t)
            if m:
                self.metadata.subsection    = int(m.group(1))
                self.metadata.subsubsection = None
        elif level == 4:
            m = re.match(r"^([a-z])\.\s*(.*)", t)
            if m:
                self.metadata.subsubsection = m.group(1)

        self.metadata.current_header = t
        self.metadata.header_level   = level

    def _extract_page(self, text: str) -> Optional[int]:
        m = self.PAGE_RE.search(text)
        if m:
            return int(m.group(1) or m.group(2))
        return None

    def _extract_images(self, text: str) -> Union[bool, List[Dict[str, str]]]:
        raw_matches = self.IMAGE_RE.findall(text)
        if not raw_matches:
            return False

        _MIME_MAP = {
            ".png":  "image/png",
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif":  "image/gif",
            ".webp": "image/webp",
            ".bmp":  "image/bmp",
        }

        result: List[Dict[str, str]] = []
        for img_path in sorted(set(raw_matches)):
            img_path = img_path.strip()
            if self._img_prefix and not img_path.startswith(self._img_prefix):
                full_path_str = f"{self._img_prefix}/{img_path}"
            else:
                full_path_str = img_path

            ext = Path(img_path).suffix.lower()
            entry: Dict[str, str] = {
                "path":      full_path_str,
                "filename":  Path(img_path).name,
                "mime_type": _MIME_MAP.get(ext, "application/octet-stream"),
            }

            try:
                img_file = Path(full_path_str)
                if not img_file.is_absolute():
                    candidate = self._extraction_dir / full_path_str
                    if candidate.exists():
                        img_file = candidate
                    else:
                        fallback_matches = list(
                            (self._extraction_dir / self._img_prefix).rglob(Path(img_path).name)
                        )
                        if fallback_matches:
                            img_file = fallback_matches[0]
                img_bytes = img_file.read_bytes()
                
                # Upload to MinIO if configured
                import boto3
                import os
                from dotenv import load_dotenv
                load_dotenv()
                
                MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
                MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER")
                MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD")
                MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME")
                
                if MINIO_ENDPOINT and MINIO_ROOT_USER and MINIO_ROOT_PASSWORD and MINIO_BUCKET_NAME:
                    import hashlib
                    import re
                    s3_client = boto3.client(
                        's3',
                        endpoint_url=MINIO_ENDPOINT,
                        aws_access_key_id=MINIO_ROOT_USER,
                        aws_secret_access_key=MINIO_ROOT_PASSWORD,
                        region_name='us-east-1'
                    )
                    
                    path_hash = hashlib.md5(full_path_str.encode('utf-8', errors='replace')).hexdigest()[:8]
                    basename = img_file.name
                    basename = re.sub(r'[^\w\-.]', '_', basename)
                    minio_filename = f"{path_hash}_{basename}"
                    
                    try:
                        s3_client.head_object(Bucket=MINIO_BUCKET_NAME, Key=minio_filename)
                    except Exception as e:
                        if getattr(e, 'response', {}).get('Error', {}).get('Code') == '404':
                            s3_client.put_object(
                                Bucket=MINIO_BUCKET_NAME,
                                Key=minio_filename,
                                Body=img_bytes,
                                ContentType=entry.get("mime_type", "image/png")
                            )
                    
                    base_url = MINIO_ENDPOINT.rstrip('/')
                    minio_url = f"{base_url}/{MINIO_BUCKET_NAME}/{minio_filename}"
                    entry["minio_url"] = minio_url
                else:
                    entry["base64"] = base64.b64encode(img_bytes).decode("utf-8")
            except Exception as exc:
                entry["base64"] = None
                entry["error"]  = str(exc)

            result.append(entry)
        return result

    def _clean_chunk_content(self, text: str) -> str:
        return self.content_cleaner.clean_text(text)

    def _should_skip_chunk(self, text: str) -> bool:
        return self.content_cleaner.should_skip_chunk(text)

    def _merge_small_chunks(self, chunks: List[ChunkWithMetadata]) -> List[ChunkWithMetadata]:
        if not chunks:
            return chunks
        merged: List[ChunkWithMetadata] = []
        for chunk in chunks:
            if len(chunk.content) < self.min_chunk_size and merged:
                prev = merged[-1]
                pv = prev.metadata.has_visual_content
                cv = chunk.metadata.has_visual_content
                if isinstance(pv, list) or isinstance(cv, list):
                    seen_paths: set = set()
                    combined: List[Dict[str, str]] = []
                    for item in (pv if isinstance(pv, list) else []) + (cv if isinstance(cv, list) else []):
                        p = item.get("path", "")
                        if p not in seen_paths:
                            seen_paths.add(p)
                            combined.append(item)
                    combined_visual: Union[bool, List[Dict[str, str]]] = combined if combined else False
                elif pv or cv:
                    combined_visual = pv or cv
                else:
                    combined_visual = False

                merged_chunk = ChunkWithMetadata(
                    content  = prev.content + "\n\n" + chunk.content,
                    metadata = chunk.metadata,
                )
                merged_chunk.metadata.has_visual_content = combined_visual
                merged[-1] = merged_chunk
            else:
                merged.append(chunk)
        return merged

    def chunk(self, text: str, img_prefix: str = "") -> List[ChunkWithMetadata]:
        self.metadata = HierarchyMetadata(
            mata_pelajaran=self.mata_pelajaran,
            id_kelas=self.id_kelas,
            jenjang=self.jenjang,
            id_guru=self.id_guru,
        )
        self._img_prefix = img_prefix
        chunks: List[ChunkWithMetadata] = []
        current_chunk: List[str] = []
        current_chunk_size = 0
        current_images: List[Dict[str, str]] = []

        def flush_current_chunk() -> None:
            nonlocal current_chunk, current_chunk_size, current_images
            if not current_chunk:
                return
            raw_text   = "\n".join(current_chunk).strip()
            chunk_text = self._clean_chunk_content(raw_text)
            if chunk_text and not self._should_skip_chunk(chunk_text):
                chunk_meta = HierarchyMetadata(**self.metadata.__dict__)
                chunk_meta.has_visual_content = current_images if current_images else False
                chunks.append(ChunkWithMetadata(content=chunk_text, metadata=chunk_meta))
            current_chunk      = []
            current_chunk_size = 0
            current_images     = []

        for line in text.splitlines():
            header_match = self.HEADER_RE.match(line)
            if header_match:
                flush_current_chunk()
                level = len(header_match.group("hashes"))
                self._parse_header_title(header_match.group("title").rstrip(), level)
                continue

            page_num = self._extract_page(line)
            if page_num:
                self.metadata.page = page_num

            images = self._extract_images(line)
            if images:
                current_images.extend(images)

            if line.strip():
                current_chunk.append(line)
                current_chunk_size += len(line) + 1

            if current_chunk_size >= self.chunk_size:
                flush_current_chunk()

        flush_current_chunk()
        return self._merge_small_chunks(chunks)

    @staticmethod
    def chunks_to_documents(
        chunks: List[ChunkWithMetadata],
        source_file: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        documents = []
        for idx, chunk in enumerate(chunks):
            meta = chunk.metadata.to_dict()
            meta["chunk_index"] = idx
            if source_file:
                meta["source_file"] = source_file
            documents.append({"page_content": chunk.content, "metadata": meta})
        return documents


# ── Page Range Config ────────────────────────────────────────────────────────

class PageRangeConfig:
    """Parser untuk Halaman_materi_buku.txt."""

    def __init__(self, config_file: Path) -> None:
        self.config_file = Path(config_file)
        self.page_ranges = self._parse_config()

    def _parse_config(self) -> Dict[str, Any]:
        ranges: Dict[str, Any] = {}
        with open(self.config_file, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                parts = [p.strip().strip('"').strip() for p in line.split(":")]
                if len(parts) < 2:
                    continue
                try:
                    pdf_name  = parts[0]
                    base_stem = Path(pdf_name).stem
                    filename  = f"{base_stem}_FINAL_PAGINATED.md"

                    range_str   = parts[1]
                    range_parts = range_str.split("-")
                    if len(range_parts) != 2:
                        continue
                    start_page = int(range_parts[0].strip())
                    end_page   = int(range_parts[1].strip())

                    mata_pelajaran = parts[2] if len(parts) > 2 else None
                    jenjang_raw      = parts[3] if len(parts) > 3 else None
                    jenjang = jenjang_raw if jenjang_raw else None

                    ranges[filename] = {
                        "page_range":     (start_page, end_page),
                        "mata_pelajaran": mata_pelajaran,
                        "jenjang":        jenjang,
                    }
                except (ValueError, IndexError):
                    continue
        return ranges

    def _match(self, filename: str) -> Optional[Dict[str, Any]]:
        if filename in self.page_ranges:
            return self.page_ranges[filename]
        stem = Path(filename).stem
        for key, val in self.page_ranges.items():
            if Path(key).stem == stem:
                return val
        return None

    def get_page_range(self, filename: str) -> Optional[Tuple[int, int]]:
        entry = self._match(filename)
        return entry["page_range"] if entry else None

    def get_book_metadata(self, filename: str) -> Dict[str, Any]:
        entry = self._match(filename)
        if entry is None:
            return {"mata_pelajaran": None, "jenjang": None}
        return {
            "mata_pelajaran": entry.get("mata_pelajaran"),
            "jenjang":        entry.get("jenjang"),
        }

    def print_config(self) -> None:
        print("Page Range Configuration:")
        print("-" * 80)
        for fn, info in sorted(self.page_ranges.items()):
            s, e = info["page_range"]
            mp   = info.get("mata_pelajaran") or "-"
            kls  = info.get("jenjang") or "-"
            print(f"{fn:<65} pages {s:>3}-{e:>3}  |  {mp}  (Kelas {kls})")
        print(f"Total files configured: {len(self.page_ranges)}")


# ── Page Range Aware Chunker ─────────────────────────────────────────────────

class PageRangeAwareChunker(HierarchyAwareChunker):
    """Extended HierarchyAwareChunker dengan page range filter."""

    def __init__(
        self,
        chunk_size:     int = 500,
        min_chunk_size: int = 150,
        page_range:     Optional[Tuple[int, int]] = None,
        mata_pelajaran: Optional[str] = None,
        id_kelas:       Optional[str] = None,
        jenjang:        Optional[str] = None,
        id_guru:        Optional[str] = None,
        extraction_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(
            chunk_size=chunk_size,
            min_chunk_size=min_chunk_size,
            mata_pelajaran=mata_pelajaran,
            id_kelas=id_kelas,
            jenjang=jenjang,
            id_guru=id_guru,
            extraction_dir=extraction_dir,
        )
        self.page_range = page_range

    def chunk(self, text: str, img_prefix: str = "") -> List[ChunkWithMetadata]:
        chunks = super().chunk(text, img_prefix=img_prefix)
        if self.page_range:
            start_page, end_page = self.page_range
            filtered = [
                c for c in chunks
                if c.metadata.page is not None and start_page <= c.metadata.page <= end_page
            ]
            print(f"  Page filter {start_page}-{end_page}: {len(chunks)} chunks → {len(filtered)} in range")
            return filtered
        return chunks


# ── Step 3 Function ──────────────────────────────────────────────────────────

def step3_chunk(config: PipelineConfig, md_paths: Optional[List[Path]] = None) -> List[Path]:
    """
    Baca Markdown final, clean headers, chunk, filter page range, simpan JSONL.

    Hasil disimpan terpusat di:
      outputs/chunks/<nama>_chunks.jsonl

    Returns: list path JSONL chunks yang dihasilkan.
    """
    print("=" * 60)
    print("  STEP 3 — Chunking + Cleaning")
    print("=" * 60)
    print(f"  Output chunks : {config.chunks_dir}/")
    print("=" * 60)

    # Direktori tempat file markdown diekstrak (terpusat di outputs/extracted/)
    extraction_dir = config.extracted_dir

    # Cari markdown files di folder terpusat
    if md_paths is None:
        md_files = list(extraction_dir.glob(config.file_pattern))
        # Fallback ke output_base jika folder terpusat kosong
        if not md_files:
            md_files = list(config.output_base.glob(config.file_pattern))
    else:
        md_files = [p for p in md_paths if p.exists()]

    if not md_files:
        print("⚠️  Tidak ada Markdown files ditemukan.")
        return []

    print(f"\nFound {len(md_files)} markdown files")

    # Load config jika ada
    cfg_obj: Optional[PageRangeConfig] = None
    if config.config_file and config.config_file.exists():
        cfg_obj = PageRangeConfig(config.config_file)
        print(f"Config loaded: {len(cfg_obj.page_ranges)} entries from {config.config_file}")
        cfg_obj.print_config()
    else:
        print(f"⚠️  Config file tidak ditemukan: {config.config_file}")
        print("   Akan dijalankan tanpa page range filter.")
    print()

    jsonl_paths: List[Path] = []
    results: Dict[str, Any] = {}

    for idx, md_file in enumerate(md_files, 1):
        filename = md_file.name
        print(f"[{idx}/{len(md_files)}] {filename}")
        print("-" * 80)

        # Cek config
        if cfg_obj and cfg_obj.get_page_range(filename) is None:
            print("⚠️  File tidak ada di konfigurasi, skipping...")
            results[filename] = {"status": "skipped", "reason": "Not found in page range config"}
            print()
            continue

        try:
            # Hitung img_prefix
            try:
                img_prefix = md_file.parent.relative_to(extraction_dir).as_posix()
            except ValueError:
                img_prefix = md_file.parent.name

            # Book metadata
            page_range     = None
            mata_pelajaran = None
            id_kelas       = None
            jenjang        = None
            id_guru        = None
            if cfg_obj:
                page_range = cfg_obj.get_page_range(filename)
                book_meta  = cfg_obj.get_book_metadata(filename)
                mata_pelajaran = book_meta.get("mata_pelajaran")
                id_kelas       = book_meta.get("id_kelas")
                jenjang        = book_meta.get("jenjang")
                id_guru        = book_meta.get("id_guru")

            # Gunakan nilai dari PipelineConfig sebagai fallback
            # (jika config file tidak menyediakan, atau tidak ada config file sama sekali)
            if mata_pelajaran is None and config.mata_pelajaran:
                mata_pelajaran = config.mata_pelajaran
            if id_kelas is None and config.id_kelas:
                id_kelas = config.id_kelas
            if jenjang is None and config.jenjang:
                jenjang = config.jenjang
            if id_guru is None and config.id_guru:
                id_guru = config.id_guru

            if page_range:
                print(f"  Page range     : {page_range[0]} - {page_range[1]}")
            print(f"  Mata pelajaran : {mata_pelajaran or '(tidak tersedia)'}")
            print(f"  ID Kelas       : {id_kelas or '(tidak tersedia)'}")
            print(f"  Jenjang        : {jenjang or '(tidak tersedia)'}")
            print(f"  ID Guru        : {id_guru or '(tidak tersedia)'}")

            print(f"  Reading   : {md_file.name}")
            text = md_file.read_text(encoding="utf-8")

            print(f"  Cleaning  : headers...")
            cleaner = MarkdownHeaderCleaner()
            cleaned_text, header_count, changed_count = cleaner.fix_markdown_headers(text)
            print(f"             {header_count} headers, {changed_count} changed")

            print(f"  Chunking  : (img_prefix='{img_prefix}')")
            chunker = PageRangeAwareChunker(
                chunk_size=config.chunk_size,
                min_chunk_size=config.min_chunk_size,
                page_range=page_range,
                mata_pelajaran=mata_pelajaran,
                id_kelas=id_kelas,
                jenjang=jenjang,
                id_guru=id_guru,
                extraction_dir=extraction_dir,
            )
            chunks = chunker.chunk(cleaned_text, img_prefix=img_prefix)
            print(f"             {len(chunks)} chunks")

            docs = PageRangeAwareChunker.chunks_to_documents(chunks, source_file=md_file.stem)

            # Simpan ke folder terpusat outputs/chunks/
            out_path = config.chunks_dir / f"{md_file.stem}_chunks.jsonl"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                for doc in docs:
                    f.write(json.dumps(doc, ensure_ascii=False) + "\n")
            print(f"  Saved     : {out_path}")
            jsonl_paths.append(out_path)

            pr_str = f"{page_range[0]}-{page_range[1]}" if page_range else None
            results[filename] = {
                "status": "success", "chunks": len(docs),
                "page_range": pr_str, "mata_pelajaran": mata_pelajaran, "id_kelas": id_kelas, "jenjang": jenjang, "id_guru": id_guru,
            }
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[filename] = {"status": "error", "error": str(e)}
        print()

    # Summary
    print("=" * 80)
    print("BATCH CHUNKING SUMMARY")
    print("=" * 80)
    success_count = sum(1 for r in results.values() if r.get("status") == "success")
    error_count   = sum(1 for r in results.values() if r.get("status") == "error")
    skipped_count = sum(1 for r in results.values() if r.get("status") == "skipped")
    total_chunks  = sum(r.get("chunks", 0) for r in results.values() if r.get("status") == "success")
    print(f"✅ Success : {success_count}/{len(md_files)}")
    print(f"❌ Errors  : {error_count}")
    print(f"⚠️  Skipped : {skipped_count}")
    print(f"📊 Total chunks generated: {total_chunks}")
    print()

    return jsonl_paths


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — INGEST KE QDRANT (HYBRID)
# ══════════════════════════════════════════════════════════════════════════════

def step4_ingest(config: PipelineConfig, jsonl_paths: Optional[List[Path]] = None) -> None:
    """
    Load JSONL chunks, encode dense + sparse, upsert ke Qdrant.
    Butuh GPU untuk encoding optimal.

    Model diambil dari model_registry (singleton) — tidak perlu load ulang
    jika sudah di-preload saat startup.
    """
    import builtins
    def print(*args, **kwargs):
        kwargs.setdefault('flush', True)
        builtins.print(*args, **kwargs)

    import torch
    import numpy as np
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, SparseVectorParams, SparseIndexParams,
        SparseVector, PointStruct,
    )

    # ── Import model dari centralized registry ─────────────────────────────
    from model_registry import get_dense_model, get_sparse_model, ProxySparseModel as SpladeEncoder

    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 60)
    print("  STEP 4 — Ingest Hybrid ke Qdrant")
    print("=" * 60)
    print(f"  Device : {DEVICE}")
    print(f"  Qdrant : {config.qdrant_host}:{config.qdrant_port} → {config.collection_name}")
    print(f"  Dense  : {config.dense_model_name}")
    print(f"  Sparse : {config.sparse_model_name}")
    print("=" * 60)

    # ── Metadata helpers ──────────────────────────────────────────────────────
    def remove_base64_recursive(obj):
        """Strip base64 dari semua field KECUALI has_visual_content — digunakan
        hanya untuk membersihkan sisa metadata yang tidak perlu."""
        if isinstance(obj, dict):
            return {k: remove_base64_recursive(v) for k, v in obj.items() if k.lower() != "base64"}
        if isinstance(obj, list):
            return [remove_base64_recursive(x) for x in obj]
        return obj

    def normalize_visual_metadata(value):
        """Normalisasi has_visual_content — base64 DIPERTAHANKAN di setiap entry.

        Setiap entry yang dihasilkan berformat:
          {
            "path"      : str,   # path relatif gambar
            "filename"  : str,   # nama file
            "mime_type" : str,   # MIME type
            "base64"    : str,   # konten gambar ter-encode base64 (jika tersedia)
          }
        """
        if not value:
            return False
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return False
        cleaned = []
        seen_paths = set()
        for item in value:
            if isinstance(item, str):
                path = item.strip()
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                cleaned.append({
                    "path":      path,
                    "filename":  Path(path).name,
                    "mime_type": "application/octet-stream",
                })
            elif isinstance(item, dict):
                # JANGAN strip base64 dari visual item — justru kita simpan
                path = str(item.get("path") or item.get("file") or item.get("filename") or "").strip()
                if not path or path in seen_paths:
                    continue
                seen_paths.add(path)
                entry: Dict[str, str] = {
                    "path":      path,
                    "filename":  str(item.get("filename") or Path(path).name),
                    "mime_type": str(item.get("mime_type") or "application/octet-stream"),
                }
                # Pertahankan base64 jika tersedia
                if item.get("base64"):
                    entry["base64"] = item["base64"]
                cleaned.append(entry)
        return cleaned if cleaned else False

    def normalize_metadata(meta, fallback_source_file):
        if not isinstance(meta, dict):
            meta = {}
        # Simpan has_visual_content (dengan base64) SEBELUM remove_base64_recursive dipanggil
        raw_visual = meta.get("has_visual_content")
        meta = remove_base64_recursive(meta)
        # Kembalikan has_visual_content asli (dengan base64) lalu normalisasi
        if raw_visual is not None:
            meta["has_visual_content"] = raw_visual
        meta["source_file"] = str(meta.get("source_file") or fallback_source_file)
        meta["has_visual_content"] = normalize_visual_metadata(meta.get("has_visual_content"))
        return meta

    def is_valid_content(text):
        text = (text or "").strip()
        if not text:
            return False
        if text in {"---", "<br>", "<br/>", "<br />"}:
            return False
        return True

    # ── Load models (dari registry — singleton, tidak load ulang) ──────────
    splade = get_sparse_model()
    dense_model = get_dense_model()

    def embed_documents(texts: List[str]) -> List[List[float]]:
        """Wrapper untuk dense embedding batch."""
        passages = [f"passage: {t.strip()}" for t in texts]
        return dense_model.encode(
            passages, batch_size=32, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        ).tolist()

    sample    = dense_model.encode(["query: test"], normalize_embeddings=True, convert_to_numpy=True)[0]
    DENSE_DIM = len(sample)
    print(f"Dense vector dim: {DENSE_DIM}")

    # ── Load chunks dari folder terpusat outputs/chunks/ ─────────────────────
    if jsonl_paths is None:
        if not config.chunks_dir.exists():
            print(f"❌ Folder chunks tidak ditemukan: {config.chunks_dir.resolve()}")
            return
        jsonl_paths = sorted(config.chunks_dir.glob("*.jsonl"))

    print(f"\n📁 {len(jsonl_paths)} JSONL files ditemukan\n")

    chunks = []
    for jf in jsonl_paths:
        print(f"   • {jf.name}", end=" ")
        count_before = len(chunks)
        try:
            with open(jf, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = item.get("page_content") or item.get("content") or item.get("text") or ""
                    content = str(content).strip()
                    if not is_valid_content(content):
                        continue
                    meta = normalize_metadata(item.get("metadata", {}), fallback_source_file=jf.stem.replace("_chunks", ""))
                    chunks.append({"page_content": content, "metadata": meta})
        except Exception as e:
            print(f"\n      ❌ {e}")
            continue
        print(f"→ {len(chunks) - count_before} chunks")

    print(f"\n✅ Total: {len(chunks)} chunks")

    if not chunks:
        print("❌ Tidak ada chunks untuk diingest!")
        return

    # ── Setup Qdrant ──────────────────────────────────────────────────────────
    qdrant_host = config.qdrant_host
    api_key = os.getenv("QDRANT_API_KEY", "")
    
    if qdrant_host.startswith("http://") or qdrant_host.startswith("https://"):
        client = QdrantClient(
            url=f"{qdrant_host}:{config.qdrant_port}",
            api_key=api_key if api_key else None,
            timeout=config.qdrant_timeout,
            check_compatibility=False
        )
    else:
        client = QdrantClient(
            host=qdrant_host,
            port=config.qdrant_port,
            api_key=api_key if api_key else None,
            https=False,
            timeout=config.qdrant_timeout,
            check_compatibility=False
        )
    print(f"\n✅ Connected: {config.qdrant_host}:{config.qdrant_port}")

    if config.force_reindex and client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)
        print(f"🗑️  Deleted existing collection: {config.collection_name}")

    if not client.collection_exists(config.collection_name):
        client.create_collection(
            collection_name=config.collection_name,
            vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
        )
        print(f"✅ Collection '{config.collection_name}' dibuat")
    else:
        print(f"ℹ️  Collection '{config.collection_name}' sudah ada, skip create.")

    # ── Ingest ────────────────────────────────────────────────────────────────
    def make_point_id(doc):
        meta = doc.get("metadata", {})
        raw = "|".join([
            str(meta.get("source_file", "unknown")),
            str(meta.get("page", "")),
            str(meta.get("chunk_index", "")),
            str(meta.get("mata_pelajaran", "")),
            str(meta.get("id_kelas", "")),
            str(meta.get("id_guru", "")),
            str(meta.get("jenjang", "")),
            hashlib.md5(doc["page_content"].encode("utf-8")).hexdigest(),
        ])
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))

    def _normalize_source_file_for_qdrant(raw: str) -> str:
        """Normalisasi source_file sebelum disimpan ke Qdrant.

        Logika HARUS identik dengan _normalize_source_file di tools.py
        agar filter retriever selalu match dengan data yang tersimpan.

        Contoh:
          "Biologi_Kelas_X_FINAL_PAGINATED" → "biologi_kelas_x"
          "Biologi_Kelas_X"                 → "biologi_kelas_x"
        """
        name = raw.strip().replace("\\", "/")
        name = Path(name).stem
        for suffix in ("_chunks", "_FINAL_PAGINATED", "_final_paginated", "_structure"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        return name.lower()

    def build_payload(doc):
        """
        Bangun payload Qdrant yang flat dan efisien.

        Field yang disimpan (tanpa duplikasi):
          page_content      - teks chunk
          source_file       - nama file sumber (dinormalisasi: lowercase, tanpa suffix pipeline)
          page              - nomor halaman
          chunk_index       - indeks chunk dalam dokumen
          mata_pelajaran    - mata pelajaran (dari config)
          kelas             - tingkat kelas (dari config)
          chapter           - judul bab (mis. "Bab 1 ...")
          chapter_num       - nomor bab (int)
          section           - judul seksi (mis. "A. Pengantar")
          section_letter    - huruf seksi (mis. "A")
          subsection        - nomor sub-seksi (int)
          subsubsection     - huruf sub-sub-seksi (mis. "a")
          current_header    - header aktif saat chunk dibuat
          header_level      - level header (1–6)
          has_visual_content- list of {path, base64} atau False
        """
        meta    = normalize_metadata(doc.get("metadata", {}), fallback_source_file="unknown")
        visuals = normalize_visual_metadata(meta.get("has_visual_content"))

        # Sederhanakan visual: hanya simpan path + base64 (filename & mime_type bisa diturunkan dari path)
        if isinstance(visuals, list):
            visuals = [
                {k: v for k, v in entry.items() if k in ("path", "base64") and v}
                for entry in visuals
            ] or False

        # Normalisasi source_file agar konsisten dengan retriever filter
        raw_source = meta.get("source_file", "unknown")
        normalized_source = _normalize_source_file_for_qdrant(raw_source)

        payload = {
            "page_content":       doc["page_content"],
            "source_file":        normalized_source,
            "buku_id":            config.buku_id,
            "page":               meta.get("page"),
            "chunk_index":        meta.get("chunk_index"),
            "mata_pelajaran":     meta.get("mata_pelajaran"),
            "id_kelas":           meta.get("id_kelas"),
            "jenjang":            meta.get("jenjang"),
            "id_guru":            meta.get("id_guru"),
            # Hierarchy — hanya field yang terisi (None di-skip di bawah)
            "chapter":            meta.get("chapter"),
            "chapter_num":        meta.get("chapter_num"),
            "section":            meta.get("section"),
            "section_letter":     meta.get("section_letter"),
            "subsection":         meta.get("subsection"),
            "subsubsection":      meta.get("subsubsection"),
            "current_header":     meta.get("current_header"),
            "header_level":       meta.get("header_level"),
            # Visual: {path, base64} saja — hapus filename & mime_type (bisa didapat dari path)
            "has_visual_content": visuals if visuals else None,
        }
        # Buang semua field None / list kosong agar payload seminimal mungkin
        return {k: v for k, v in payload.items() if v is not None and v != [] and v is not False}

    BATCH_SIZE    = config.batch_size
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    ingested      = 0

    print(f"\n🔄 Ingesting {len(chunks)} chunks (batch_size={BATCH_SIZE})\n")

    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start : batch_start + BATCH_SIZE]
        texts = [doc["page_content"] for doc in batch]

        dense_vecs  = embed_documents(texts)
        sparse_vecs = splade.encode_passages(texts)

        points = []
        for doc, dvec, svec in zip(batch, dense_vecs, sparse_vecs):
            points.append(PointStruct(
                id      = make_point_id(doc),
                vector  = {
                    "dense":  dvec,
                    "sparse": SpladeEncoder.to_qdrant(svec),
                },
                payload = build_payload(doc),
            ))

        try:
            client.upsert(collection_name=config.collection_name, points=points, wait=True)
            ingested  += len(points)
            batch_num  = batch_start // BATCH_SIZE + 1
            print(f"   Batch {batch_num:>4}/{total_batches}  +{len(points):>4} pts  →  total {ingested:>6}")
        except Exception as e:
            print(f"   ❌ Batch {batch_start // BATCH_SIZE + 1} error: {e}")
            continue

    # Summary
    final_count = client.count(config.collection_name, exact=True).count
    print(f"\n{'='*60}")
    print(f"  ✅ INGEST SELESAI")
    print(f"  Collection   : {config.collection_name}")
    print(f"  Points       : {final_count:,}")
    print(f"  Dense        : {DENSE_DIM}-dim  ({config.dense_model_name})")
    print(f"  Sparse       : SPLADE  ({config.sparse_model_name})")
    print(f"  Payload      : flat (chapter/section/header + has_visual_content {{path,base64}})")
    print(f"  Search mode  : Hybrid RRF (dense + sparse)")
    print(f"{'='*60}")


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

def run_full_pipeline(config: PipelineConfig, step: Optional[str] = None) -> None:
    """Jalankan pipeline penuh atau step tertentu."""

    pipeline_start = datetime.now()

    print("\n" + "█" * 60)
    print("  RAG PIPELINE — PDF → Qdrant")
    print("█" * 60)
    print(f"  Waktu mulai : {pipeline_start.strftime('%Y-%m-%d %H:%M:%S')}")
    if step:
        print(f"  Step         : {step}")
    else:
        print(f"  Step         : ALL (extract → describe → chunk → ingest)")
    print("█" * 60 + "\n")

    if step is None or step == "extract":
        json_paths = step1_extract(config)
        if step == "extract":
            return
    else:
        json_paths = None

    if step is None or step == "describe":
        md_paths = step2_describe_images(config, json_paths)
        if step == "describe":
            return
    else:
        md_paths = None

    if step is None or step == "chunk":
        jsonl_paths = step3_chunk(config, md_paths)
        if step == "chunk":
            return
    else:
        jsonl_paths = None

    if step is None or step == "ingest":
        step4_ingest(config, jsonl_paths)

    elapsed = (datetime.now() - pipeline_start).seconds
    print(f"\n{'█'*60}")
    print(f"  PIPELINE SELESAI — {elapsed // 60}m {elapsed % 60}s")
    print(f"{'█'*60}\n")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="RAG Pipeline: PDF → Ekstraksi → Multimodal → Chunking → Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python execution/full_pipeline.py --input-folder "Kelas 10"
  python execution/full_pipeline.py --step extract
  python execution/full_pipeline.py --step chunk --config Halaman_materi_buku.txt
  python execution/full_pipeline.py --step ingest --qdrant-host 76.13.195.1
        """,
    )

    parser.add_argument("--step", choices=["extract", "describe", "chunk", "ingest"],
                        help="Jalankan step tertentu saja (default: semua)")
    parser.add_argument("--input-pdf", type=str, default=None,
                        help="Path ke SATU file PDF yang akan diproses. "
                             "Jika diset, --input-folder diabaikan oleh Step 1.")
    parser.add_argument("--input-folder", type=str, default="Kelas 10",
                        help="Folder berisi PDF input (default: 'Kelas 10'). "
                             "Diabaikan jika --input-pdf diset.")
    parser.add_argument("--output-base", type=str, default=".",
                        help="Base directory untuk output (default: '.')")
    parser.add_argument("--outputs-root", type=str, default="outputs",
                        help="Root folder terpusat untuk semua artefak pipeline (default: 'outputs')")
    parser.add_argument("--config", type=str, default=None,
                        help="Path ke Halaman_materi_buku.txt")
    parser.add_argument("--qdrant-host", type=str, default="76.13.195.1")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    parser.add_argument("--collection", type=str, default="test_pipeline")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--force-reindex", action="store_true",
                        help="Hapus dan buat ulang collection Qdrant")
    parser.add_argument("--no-skip", action="store_true",
                        help="Jangan skip file yang sudah diproses")
    parser.add_argument("--start-page", type=int, default=0,
                        help="Halaman awal ekstraksi (1-based). 0 = dari awal dokumen")
    parser.add_argument("--end-page", type=int, default=0,
                        help="Halaman akhir ekstraksi (inklusif). 0 = sampai akhir dokumen")
    parser.add_argument("--mata-pelajaran", type=str, default=None,
                        help="Mata pelajaran (mis. Biologi). Dipakai sebagai metadata chunk.")
    parser.add_argument("--id-kelas", type=str, default=None,
                        help="ID Kelas (mis. X-A). Dipakai sebagai metadata chunk.")
    parser.add_argument("--vlm-model", type=str, default=DEFAULT_VLM_MODEL,
                        help=f"Nama model VLM (default: {DEFAULT_VLM_MODEL})")
    parser.add_argument("--ollama-host", type=str, default=DEFAULT_VLM_HOST,
                        help=f"Base URL server VLM (default: {DEFAULT_VLM_HOST})")
    parser.add_argument("--dense-model", type=str, default=DEFAULT_DENSE_MODEL)
    parser.add_argument("--sparse-model", type=str, default=DEFAULT_SPARSE_MODEL)

    args = parser.parse_args()

    # Resolve config file
    config_file = None
    if args.config:
        config_file = Path(args.config)
    else:
        # Coba cari di beberapa lokasi umum
        for candidate in [
            Path("Halaman_materi_buku.txt"),
            Path("../Halaman_materi_buku.txt"),
            Path(__file__).parent.parent / "Halaman_materi_buku.txt",
        ]:
            if candidate.exists():
                config_file = candidate
                break

    cfg = PipelineConfig(
        input_pdf         = Path(args.input_pdf) if args.input_pdf else None,
        input_folder      = Path(args.input_folder),
        output_base       = Path(args.output_base),
        outputs_root      = Path(args.outputs_root),
        config_file       = config_file,
        qdrant_host       = args.qdrant_host,
        qdrant_port       = args.qdrant_port,
        collection_name   = args.collection,
        batch_size        = args.batch_size,
        chunk_size        = args.chunk_size,
        force_reindex     = args.force_reindex,
        skip_existing     = not args.no_skip,
        start_page        = args.start_page,
        end_page          = args.end_page,
        mata_pelajaran    = args.mata_pelajaran,
        id_kelas          = args.id_kelas,
        jenjang           = args.jenjang,
        id_guru           = args.id_guru,
        vlm_model_id      = args.vlm_model,
        ollama_host       = args.ollama_host,
        dense_model_name  = args.dense_model,
        sparse_model_name = args.sparse_model,
    )

    run_full_pipeline(cfg, step=args.step)


if __name__ == "__main__":
    main()
