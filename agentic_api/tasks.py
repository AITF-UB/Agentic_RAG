import traceback
from pathlib import Path
from celery_app import celery_app
from full_pipeline import PipelineConfig, run_full_pipeline

# Hardcode main directories based on the ones in main.py
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("pipeline_output")

@celery_app.task(bind=True)
def run_pipeline_task(self, pdf_filename: str, params_dict: dict):
    """
    Celery task untuk menjalankan pipeline RAG asinkron.
    """
    self.update_state(state="RUNNING", meta={"message": "Pipeline dimulai..."})
    
    pdf_path = UPLOAD_DIR / pdf_filename
    
    try:
        cfg = PipelineConfig(
            input_pdf         = pdf_path,
            output_base       = OUTPUT_DIR,
            outputs_root      = OUTPUT_DIR / "outputs",
            qdrant_host       = params_dict.get("qdrant_host"),
            qdrant_port       = params_dict.get("qdrant_port"),
            collection_name   = params_dict.get("collection_for_ekstraction"),
            chunk_size        = params_dict.get("chunk_size", 1000),
            force_reindex     = params_dict.get("force_reindex", False),
            start_page        = params_dict.get("start_page", 0),
            end_page          = params_dict.get("end_page", 0),
            mata_pelajaran    = params_dict.get("mata_pelajaran"),
            id_kelas          = params_dict.get("id_kelas"),
            jenjang           = params_dict.get("jenjang"),
            id_guru           = params_dict.get("id_guru"),
            vlm_model_id      = params_dict.get("vlm_model"),
            ollama_host       = params_dict.get("ollama_host"),
            dense_model_name  = params_dict.get("dense_model"),
            sparse_model_name = params_dict.get("sparse_model"),
            skip_existing     = False,
        )

        step = params_dict.get("step")
        run_full_pipeline(cfg, step=step if step else None)

        # Hitung artefak yang dihasilkan
        json_files  = list(OUTPUT_DIR.rglob("*_structure.json"))
        md_files    = list(OUTPUT_DIR.rglob("*_FINAL_PAGINATED.md"))
        jsonl_files = list(cfg.chunks_dir.glob("*.jsonl"))
        total_chunks = sum(
            sum(1 for line in open(f, encoding="utf-8") if line.strip())
            for f in jsonl_files
        )

        return {
            "status": "success",
            "message": "Pipeline selesai.",
            "pdf_file": pdf_path.name,
            "step_run": step if step else "all",
            "json_files": [str(p.name) for p in json_files],
            "markdown_files": [str(p.name) for p in md_files],
            "jsonl_files": [str(p.name) for p in jsonl_files],
            "total_chunks": total_chunks,
            "qdrant_collection": params_dict.get("collection_for_ekstraction"),
        }

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        print(error_msg) # Cetak ke stdout worker Celery
        self.update_state(state="FAILURE", meta={
            "exc_type": type(exc).__name__,
            "exc_message": error_msg
        })
        raise exc

