# -*- coding: utf-8 -*-
import os
import base64
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
import io
import numpy as np
import uvicorn

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Pastikan API tidak mencoba memanggil dirinya sendiri
if "MODEL_API_URL" in os.environ:
    del os.environ["MODEL_API_URL"]

from model_registry import (
    get_dense_model,
    get_sparse_model,
    get_reranker,
    get_docling_converter,
    preload_all
)

app = FastAPI(title="Model API Microservice")

@app.on_event("startup")
def startup_event():
    # Preload all models on startup
    preload_all()

class DenseRequest(BaseModel):
    texts: List[str]
    normalize_embeddings: bool = True

class SparseQueryRequest(BaseModel):
    text: str

class SparsePassagesRequest(BaseModel):
    texts: List[str]

class RerankRequest(BaseModel):
    query: str
    texts: List[str]

@app.post("/embed/dense")
def embed_dense(req: DenseRequest):
    try:
        model = get_dense_model()
        vectors = model.encode(req.texts, normalize_embeddings=req.normalize_embeddings, convert_to_numpy=True)
        return {"vectors": vectors.tolist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embed/sparse/query")
def embed_sparse_query(req: SparseQueryRequest):
    try:
        model = get_sparse_model()
        result = model.encode_query(req.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/embed/sparse/passages")
def embed_sparse_passages(req: SparsePassagesRequest):
    try:
        model = get_sparse_model()
        vectors = model.encode_passages(req.texts)
        results = []
        for vec in vectors:
            nonzero_idx = np.nonzero(vec)[0]
            results.append({
                "indices": nonzero_idx.tolist(),
                "values": vec[nonzero_idx].tolist()
            })
        return {"vectors": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/rerank")
def rerank(req: RerankRequest):
    try:
        reranker = get_reranker()
        pairs = [(req.query, t) for t in req.texts]
        scores = reranker.predict(pairs, batch_size=16, show_progress_bar=False)
        # Handle scalar or array cases safely
        if isinstance(scores, np.ndarray):
            scores = scores.tolist()
        elif not isinstance(scores, list):
            scores = [scores]
        return {"scores": [float(s) for s in scores]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract/docling")
async def extract_docling(file: UploadFile = File(...)):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        converter = get_docling_converter()
        result = converter.convert(tmp_path)
        
        total_pages = len(result.document.pages) if hasattr(result.document, "pages") else 0
        
        elements = []
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
                        "type": element.label,
                        "page": page_no,
                        "text": text,
                    })
            elif element.label == "formula":
                elements.append({
                    "type": "formula",
                    "page": page_no,
                    "text": element.text,
                })
            elif element.label in ("picture", "table"):
                if hasattr(element, "image") and element.image is not None:
                    pil_img = element.image.pil_image
                    if pil_img.width < 80 or pil_img.height < 80:
                        continue
                    img_counter += 1
                    
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                    
                    elements.append({
                        "type": element.label,
                        "page": page_no,
                        "image_base64": b64_str,
                    })

        os.remove(tmp_path)
        
        return {
            "total_pages": total_pages,
            "elements": elements
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("model_api:app", host="0.0.0.0", port=8003, workers=1)
