import os
import json
import time
from datetime import datetime
from typing import Any
from jinja2 import Environment, FileSystemLoader
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from tools import RAGEngine, clean_json_from_llm, extract_source, generate_konten_id, truncate_context_to_budget
from llm import get_llm, get_eval_llm
from prompt_config import compile_leveling_registry, compile_subject_registry

env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")))
llm = get_llm()

def load_prompt(template_name: str, **kwargs) -> str:
    template = env.get_template(template_name)
    return template.render(**kwargs)

MAPEL_MAPPING = {
    # Mapping berdasar ID (MVP)
    "1": "Bahasa Indonesia",
    "2": "Bahasa Indonesia",
    "17": "Ilmu Pengetahuan Sosial",
    "5": "Informatika",
    "6": "Koding dan Kecerdasan Artifisial",
    "10": "Matematika",
    "8": "Pendidikan Agama Islam dan Budi Pekerti",
    "9": "Pendidikan Agama Katolik dan Budi Pekerti",
    "11": "Pendidikan Jasmani, Olahraga, dan Kesehatan",
    "12": "Pendidikan Pancasila",
    "18": "Seni Rupa",
    "19": "Seni Tari",
    "20": "Seni Teater",
    # Mapping legacy text (fallback)
    "bio": "Biologi",
    "bahasa_indonesia": "Bahasa Indonesia",
    "bindo": "Bahasa Indonesia",
    "matematika_umum": "Matematika",
    "mat": "Matematika",
    "matematika": "Matematika",
    "mtk": "Matematika",
    "ips": "Ilmu Pengetahuan Sosial"
}

def resolve_mapel(raw_mapel: Any) -> str:
    if not raw_mapel: return ""
    raw_str = str(raw_mapel)
    key = raw_str.lower().replace(" ", "_")
    return MAPEL_MAPPING.get(key, raw_str)

# ================================================================
# 1. NODES
# ================================================================
async def retrieve_node(state: AgentState) -> dict:
    """Melakukan pencarian ke Qdrant menggunakan RAGEngine secara asynchronous."""
    tipe = state["tipe"]
    req = state["request_params"]
    
    # Fokuskan query RAG HANYA pada elemen dan materi.
    query = f"{req.get('materi', '')}".strip()
    
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    
    # Ekstrak angka kelas dari jenjang (mendukung angka & romawi)
    jenjang_str = str(req.get("jenjang", "")).lower().strip()
    kelas_int = None
    
    roman_map = {"X": 10, "xi": 11, "xii": 12}
    if jenjang_str in roman_map:
        kelas_int = roman_map[jenjang_str]
    else:
        digits = ''.join(filter(str.isdigit, jenjang_str))
        if digits:
            kelas_int = int(digits)
    
    buku_id = req.get("buku_id")
    user_id = req.get("user_id")
    if user_id:
        print(f"[retrieve_node] Generating for user={user_id}, buku={buku_id}")
    rag_results = await RAGEngine.unified_search(query, tipe, mapel=mapel_str, kelas=kelas_int, buku_id=buku_id)
    
    # Format texts
    text_ctx_parts = []
    for t in rag_results["text"]:
        part = t["text"]
        vis = t.get("visual_context", [])
        if isinstance(vis, str):
            vis = [vis]
        if vis:
            vis_str = ", ".join([os.path.basename(v.get("path", "")) if isinstance(v, dict) else os.path.basename(str(v)) for v in vis])
            part = f"[Referensi File Gambar: {vis_str}]\n" + part
        text_ctx_parts.append(part)
        
    text_ctx = "\n---\n".join(text_ctx_parts)
    sumber = extract_source(rag_results["text"])

    # Build formatted image context string
    img_ctx_str = ""
    visual_assets = {}
    if rag_results["images"]:
        for idx, img_info in enumerate(rag_results["images"]):
            img_id = img_info.get("id", f"IMG-{idx+1:03d}")
            img_path = img_info["path"]
            img_context = img_info["context"].replace("\n", " ") # Bersihkan newline agar rapi
            img_ctx_str += f"[{img_id}] (filename: {os.path.basename(img_path)}) - Deskripsi: {img_context}...\n\n"
            
            # Extract base64 for frontend
            b64_data = img_info.get("base64")
            if b64_data:
                mime_type = img_info.get("mime_type", "image/png")
                if b64_data.startswith("data:"):
                    visual_assets[img_id] = b64_data
                else:
                    visual_assets[img_id] = f"data:{mime_type};base64,{b64_data}"
        
    max_rag_tokens_str = os.getenv("MAX_RAG_TOKEN")
    if max_rag_tokens_str and max_rag_tokens_str.isdigit():
        max_rag_tokens = int(max_rag_tokens_str)
        text_ctx = truncate_context_to_budget(text_ctx, max_tokens=max_rag_tokens) if text_ctx else ""
        img_ctx_str = truncate_context_to_budget(img_ctx_str, max_tokens=max_rag_tokens // 4).strip() if img_ctx_str else ""
        
    return {
        "rag_context": text_ctx if text_ctx else "Tidak ada dokumen relevan di database.",
        "sumber_text": sumber,
        "image_context": img_ctx_str.strip() if img_ctx_str else "",
        "visual_assets": visual_assets
    }

def get_rag_context_for_revision(state: AgentState) -> str:
    """Mengembalikan rag_context atau string kosong jika error murni dari gagal parsing."""
    if state["revision_count"] == 0:
        return state.get("rag_context", "")
        
    eval_res = state.get("evaluator_result", {})
    poin = str(eval_res.get("poin_revisi", ""))
    gen = state.get("generated_content", {})
    
    is_format_error = False
    if isinstance(gen, dict) and "error" in gen:
        is_format_error = True
    elif "JSON" in poin and "rusak" in poin:
        is_format_error = True
        
    if "konteks" in poin.lower() or "jauh" in poin.lower() or "materi" in poin.lower() or "rag" in poin.lower():
        is_format_error = False
        
    if is_format_error:
        return ""
    return state.get("rag_context", "")

def get_context_with_header(state: AgentState) -> str:
    req = state.get("request_params", {})
    level = state.get("level")
    raw_context = get_rag_context_for_revision(state)
    
    level_upper = (level or "").upper()
    mapping = {"LOW": "LOTS", "MID": "MOTS", "HIGH": "HOTS"}
    internal_level = mapping.get(level_upper, level_upper)

    mapel = resolve_mapel(req.get("mapel_id", ""))
    bab = req.get("elemen_label", "")
    sub_bab = req.get("materi", "")

    header_parts = []
    if mapel: header_parts.append(f"Mapel: {mapel}")
    if bab: header_parts.append(f"Bab: {bab}")
    if sub_bab: header_parts.append(f"Sub Bab: {sub_bab}")
    
    header = " | ".join(header_parts)
    if internal_level and internal_level.lower() != "none" and internal_level != "":
        if header:
            header += f" | Target: {internal_level}"
        else:
            header = f"Target: {internal_level}"
            
    context_parts = []
    if header:
        context_parts.append(header)
    if raw_context:
        context_parts.append(f"\n--- MATERI ---\n{raw_context}")
        
    return "\n".join(context_parts)

async def _call_generation_llm(state: AgentState, usr_prompt: str, is_array_output: bool = False, jumlah_soal_target: int = 0) -> dict:
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    sys_prompt = load_prompt("system.j2", matpel=mapel_str, materi=req.get("materi", ""), level=lvl)
    
    if state.get("instruksi_revisi"):
        usr_prompt += f"\n\n[INSTRUKSI REVISI DARI GURU]:\n{state['instruksi_revisi']}\nSesuaikan dan perbaiki hasil generasimu berdasarkan instruksi ini!"

    if state.get("evaluator_result") and state["revision_count"] > 0:
        usr_prompt += f"\n\n[FEEDBACK REVISI SEBELUMNYA]:\n{state['evaluator_result'].get('poin_revisi')}\nPerbaiki JSON-mu!"
        
        gen = state.get("generated_content", {})
        if isinstance(gen, dict) and "raw" in gen:
            usr_prompt += f"\n\n[OUTPUT SEBELUMNYA YANG RUSAK]:\n```text\n{gen['raw']}\n```\nTugasmu HANYA memperbaiki format JSON di atas agar valid (tambahkan kutip, kurung, koma, dll yang kurang). JANGAN mengubah isinya secara drastis."

    if is_array_output:
        array_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "array_response",
                "strict": False,
                "schema": {
                    "type": "array",
                    "items": {
                        "type": "object"
                    }
                }
            }
        }
        if jumlah_soal_target > 0:
            array_schema["json_schema"]["schema"]["minItems"] = jumlah_soal_target
            array_schema["json_schema"]["schema"]["maxItems"] = jumlah_soal_target
            
        bound_llm = llm.bind(response_format=array_schema)
    else:
        bound_llm = llm.bind(response_format={"type": "json_object"})

    response = await bound_llm.ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=usr_prompt)])
    content_dict = clean_json_from_llm(response.content)
    
    return {
        "generated_content": content_dict
    }


def _score_from_eval(eval_dict: Any) -> float:
    try:
        return float(eval_dict.get("skor", 0))
    except Exception:
        return 0.0


def _update_best_revision(state: AgentState, eval_dict: dict) -> dict:
    current_content = state.get("generated_content")
    if isinstance(current_content, dict) and "error" in current_content:
        return {}

    current_score = _score_from_eval(eval_dict)
    best_score = state.get("best_revision_score")
    if best_score is None or current_score > best_score:
        return {
            "best_revision": current_content,
            "best_evaluator_result": eval_dict,
            "best_revision_score": current_score,
            "best_revision_count": state["revision_count"] + 1
        }
    return {}

async def bacaan_node(state: AgentState) -> dict:
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    level_config = compile_leveling_registry("bacaan", lvl)
    subject_config = compile_subject_registry("bacaan", mapel_str)
    usr_prompt = load_prompt("bacaan.j2", jenjang=req["jenjang"], kelas=req.get("kelas_id", ""), atp=req.get("atp", ""), context=get_context_with_header(state), level=lvl, level_config=level_config, subject_config=subject_config)
    return await _call_generation_llm(state, usr_prompt, is_array_output=False)

async def pretest_node(state: AgentState) -> dict:
    import os
    jumlah = int(os.getenv("JUMLAH_SOAL_PRETEST", "10"))
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    level_config = compile_leveling_registry("pretest", lvl)
    subject_config = compile_subject_registry("pretest", mapel_str)
    usr_prompt = load_prompt("pretest.j2", jenjang=req["jenjang"], kelas=req.get("kelas_id", ""), atp=req.get("atp", ""), context=get_context_with_header(state), level=lvl, level_config=level_config, stimulus_config=subject_config)
    return await _call_generation_llm(state, usr_prompt, is_array_output=True, jumlah_soal_target=jumlah)

async def quiz_pg_node(state: AgentState) -> dict:
    import os
    jumlah = int(os.getenv("JUMLAH_SOAL_QUIZ_PG", "10"))
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    level_config = compile_leveling_registry("quiz_pg", lvl)
    subject_config = compile_subject_registry("quiz_pg", mapel_str)
    usr_prompt = load_prompt("quiz_pg.j2", jenjang=req["jenjang"], kelas=req.get("kelas_id", ""), atp=req.get("atp", ""), context=get_context_with_header(state), level=lvl, level_config=level_config, stimulus_config=subject_config)
    return await _call_generation_llm(state, usr_prompt, is_array_output=True, jumlah_soal_target=jumlah)

async def quiz_essay_node(state: AgentState) -> dict:
    import os
    jumlah = int(os.getenv("JUMLAH_SOAL_QUIZ_ESSAY", "5"))
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    level_config = compile_leveling_registry("quiz_essay", lvl)
    subject_config = compile_subject_registry("quiz_essay", mapel_str)
    usr_prompt = load_prompt("quiz_essay.j2", jenjang=req["jenjang"], kelas=req.get("kelas_id", ""), atp=req.get("atp", ""), context=get_context_with_header(state), level=lvl, level_config=level_config, stimulus_config=subject_config)
    return await _call_generation_llm(state, usr_prompt, is_array_output=True, jumlah_soal_target=jumlah)

async def flashcard_node(state: AgentState) -> dict:
    import os
    jumlah = int(os.getenv("JUMLAH_SOAL_FLASHCARD", "5"))
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    level_config = compile_leveling_registry("flashcard", lvl)
    subject_config = compile_subject_registry("flashcard", mapel_str)
    usr_prompt = load_prompt("flashcard.j2", jenjang=req["jenjang"], kelas=req.get("kelas_id", ""), context=get_context_with_header(state), atp=req.get("atp", ""), level=lvl, level_config=level_config)
    return await _call_generation_llm(state, usr_prompt, is_array_output=True, jumlah_soal_target=jumlah)

async def mindmap_node(state: AgentState) -> dict:
    req = state["request_params"]
    lvl = state["level"]
    mapel_str = resolve_mapel(req.get("mapel_id", ""))
    level_config = compile_leveling_registry("mindmap", lvl)
    subject_config = compile_subject_registry("mindmap", mapel_str)
    usr_prompt = load_prompt("mindmap.j2", context=get_context_with_header(state), atp=req.get("atp", ""))
    return await _call_generation_llm(state, usr_prompt, is_array_output=False)

async def evaluator_node(state: AgentState) -> dict:
    """Mengevaluasi output generator."""
    if state["revision_count"] >= 2:
        return {
            "evaluator_result": state.get("best_evaluator_result", {"skor": 0, "poin_revisi": ["Batas revisi tercapai. Menggunakan hasil revisi terbaik yang tersedia."]}),
            "generated_content": state.get("best_revision", state.get("generated_content")),
            "revision_count": state["revision_count"]
        }

    gen_content = state.get("generated_content", {})
    if isinstance(gen_content, dict) and "error" in gen_content:
        # Langsung tembak paksa revisi tanpa panggil LLM Evaluator
        return {
            "evaluator_result": {
                "skor": 0, 
                "status": "tidak_layak",
                "poin_revisi": ["JSON output sebelumnya gagal diparsing (kemungkinan terpotong atau kurang tanda koma/kurung). Perbaiki struktur JSON agar valid!"]
            },
            "revision_count": state["revision_count"] + 1
        }

    req = state["request_params"]
    sys_prompt = "Kamu adalah Evaluator JSON dan Konten Pendidikan."
    usr_prompt = load_prompt(
        "evaluator.j2",
        materi=req.get("materi", ""),
        atp=req.get("atp", ""),
        level=state["level"],
        tipe=state["tipe"],
        rag_context=state.get("rag_context", ""),
        generated_content=json.dumps(state["generated_content"], indent=2)
    )
    
    response = await get_eval_llm().ainvoke([SystemMessage(content=sys_prompt), HumanMessage(content=usr_prompt)])
    eval_dict = clean_json_from_llm(response.content)
    
    # Fallback if evaluation is weird
    if not isinstance(eval_dict, dict) or "skor" not in eval_dict:
        eval_dict = {"skor": 0, "poin_revisi": ["JSON output sebelumnya terpotong atau rusak. Buat ulang JSON dengan valid dan lengkap."]}

    update_fields = _update_best_revision(state, eval_dict)
    return {
        "evaluator_result": eval_dict,
        "revision_count": state["revision_count"] + 1,
        **update_fields
    }

def structurer_node(state: AgentState) -> dict:
    """Membungkus hasil akhir sesuai API Contract SR PSR2"""
    tipe = state["tipe"]
    req = state["request_params"]
    content = state["generated_content"]
    
    # Mapping format JSON untuk frontend
    if tipe == "bacaan":
        if isinstance(content, dict):
            content.setdefault("source", state["sumber_text"])
            
    elif tipe == "flashcard":
        if isinstance(content, list):
            content = {"cards": content, "source": state["sumber_text"]}
        elif isinstance(content, dict):
            content.setdefault("source", state["sumber_text"])
            
    elif tipe == "mindmap":
        if isinstance(content, list):
            content = {"root": {"children": content}}
        elif isinstance(content, dict) and "root" not in content:
            content = {"root": content}

    elif tipe == "quiz_essay":
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item.pop("level", None)
            content = {"pertanyaan": content}

    elif tipe in ["quiz_pg", "pretest"]:
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item.pop("level", None)
            content = {"soal": content}
        elif tipe == "flashcard":
            content = {"flashcard": content, "source": state["sumber_text"]}
            
    # Tambahkan visual assets jika direquest via image_id
    visual_assets = state.get("visual_assets", {})

    def inject_visuals(item: dict):
        if visual_assets:
            item["visualz"] = list(visual_assets.values())
        else:
            item["visualz"] = None

    if isinstance(content, dict):
        if tipe == "bacaan":
            # Set top-level visuals for bacaan if requested
            if "konten_markdown" in content:
                teks_markdown = content["konten_markdown"]
                references_to_append = []
                for img_id, b64_data in visual_assets.items():
                    if f"[{img_id}]" in teks_markdown:
                        references_to_append.append(f"[{img_id}]: {b64_data}")
                
                if references_to_append:
                    content["konten_markdown"] = teks_markdown + "\n\n" + "\n".join(references_to_append)
        
        # Injeksi visual di level paling atas (root) hanya untuk task tertentu
        if tipe in ["bacaan", "quiz_pg", "quiz_essay", "pretest"]:
            inject_visuals(content)

    return {"final_payload": content}

# ================================================================
# 2. EDGES & GRAPH
# ================================================================
def route_after_retrieve(state: AgentState) -> str:
    tipe = state.get("tipe")
    if tipe in ["bacaan", "pretest", "quiz_pg", "quiz_essay", "flashcard", "mindmap"]:
        return tipe
    raise ValueError(f"Tipe {tipe} tidak dikenali.")

def should_revise(state: AgentState) -> str:
    eval_res = state.get("evaluator_result", {})
    skor = eval_res.get("skor", 100)
    status = eval_res.get("status", "layak")
    
    if (skor < 80 or status == "tidak_layak") and state["revision_count"] < 2:
        return state.get("tipe")
    return "pass"

builder = StateGraph(AgentState)
builder.add_node("retrieve", retrieve_node)
builder.add_node("bacaan", bacaan_node)
builder.add_node("pretest", pretest_node)
builder.add_node("quiz_pg", quiz_pg_node)
builder.add_node("quiz_essay", quiz_essay_node)
builder.add_node("flashcard", flashcard_node)
builder.add_node("mindmap", mindmap_node)
builder.add_node("evaluate", evaluator_node)
builder.add_node("structure", structurer_node)

builder.add_edge(START, "retrieve")

builder.add_conditional_edges(
    "retrieve",
    route_after_retrieve,
    {
        "bacaan": "bacaan",
        "pretest": "pretest",
        "quiz_pg": "quiz_pg",
        "quiz_essay": "quiz_essay",
        "flashcard": "flashcard",
        "mindmap": "mindmap"
    }
)

for node_name in ["bacaan", "pretest", "quiz_pg", "quiz_essay", "flashcard", "mindmap"]:
    builder.add_edge(node_name, "evaluate")

builder.add_conditional_edges(
    "evaluate", 
    should_revise, 
    {
        "bacaan": "bacaan",
        "pretest": "pretest",
        "quiz_pg": "quiz_pg",
        "quiz_essay": "quiz_essay",
        "flashcard": "flashcard",
        "mindmap": "mindmap",
        "pass": "structure"
    }
)

builder.add_edge("structure", END)

beta_graph = builder.compile()
