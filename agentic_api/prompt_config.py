import os
import ast
import json
import logging

log = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
LEVELING_CRITERIA_FILE = "leveling_criteria.md"
STIMULUS_FILE = "stimulus_profile.md"

# Orchestration Table (menyesuaikan dengan task types di agentic_api)
TASKS_WITH_STIMULUS = {"quiz_pg", "pretest", "quiz_essay"}
TASKS_WITH_MIXED_LEVELS = {"pretest"}

def _read(filename: str) -> str:
    path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def _load_dict(raw: str) -> dict:
    try:
        brace_idx = raw.find("{")
        if brace_idx > 0:
            raw = raw[brace_idx:]
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return {}

def _join_natural(items: list, conjunction: str = "dan") -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"

def _compile_pedagogy_prose(task_type: str, level_data: dict) -> str:
    TASK_VERBS = {
        "bacaan": "Bangun materi",
        "flashcard": "Buat flashcard",
        "mindmap": "Susun mindmap",
    }

    kompetensi = level_data.get("kompetensi_inti", "")
    pedagogi = level_data.get("pedagogi", {})
    asesmen = level_data.get("asesmen", {})

    parts = []
    verb = TASK_VERBS.get(task_type, "Buat konten")
    if kompetensi:
        k = kompetensi[0].lower() + kompetensi[1:].rstrip(".")
        parts.append(f"{verb} yang mendorong siswa {k}.")

    fokus = pedagogi.get("fokus_pembelajaran", [])
    if fokus:
        parts.append(f"Fokuskan pembahasan pada {_join_natural(fokus)}.")

    hindari_raw = asesmen.get("hindari", [])
    if hindari_raw:
        hindari = [item for item in hindari_raw if "pertanyaan" not in item.lower()]
        if not hindari:
            hindari = ["hafalan tanpa konteks"]
        parts.append(f"Hindari {_join_natural(hindari, 'atau')}.")

    return "\n\n".join(parts)

def _compile_assessment_prose(level_data: dict) -> str:
    asesmen = level_data.get("asesmen", {})
    parts = []

    operasi = asesmen.get("operasi_kognitif", [])
    if operasi:
        parts.append(f"Buat soal yang mengukur kemampuan siswa dalam {_join_natural(operasi)}.")

    target = asesmen.get("target_pengukuran", [])
    if target:
        parts.append(f"Sasaran pengukuran: {_join_natural(target)}.")

    hindari = asesmen.get("hindari", [])
    if hindari:
        parts.append(f"Hindari soal yang hanya menguji {_join_natural(hindari, 'atau')}.")

    return "\n\n".join(parts)

def _compile_pretest_level_prose(level_key: str, level_data: dict) -> str:
    asesmen = level_data.get("asesmen", {})
    lines = [f"{level_key}:"]

    operasi = asesmen.get("operasi_kognitif", [])
    if operasi:
        lines.append(f"Ukur kemampuan siswa dalam {_join_natural(operasi)}.")

    target = asesmen.get("target_pengukuran", [])
    if target:
        lines.append(f"Sasaran: {_join_natural(target)}.")

    hindari = asesmen.get("hindari", [])
    if hindari:
        lines.append(f"Hindari soal yang hanya menguji {_join_natural(hindari, 'atau')}.")

    return "\n".join(lines)

def compile_leveling_registry(task_type: str, level: str = None) -> str:
    raw = _read(LEVELING_CRITERIA_FILE)
    if not raw: return ""
    registry = _load_dict(raw)
    if not registry: return ""

    is_assessment = task_type in TASKS_WITH_STIMULUS
    is_mixed = task_type in TASKS_WITH_MIXED_LEVELS

    if is_mixed:
        sections = []
        for lvl_key in ["LOTS", "MOTS", "HOTS"]:
            lvl_data = registry.get(lvl_key)
            if lvl_data:
                sections.append(_compile_pretest_level_prose(lvl_key, lvl_data))
        return "\n\n".join(sections)
    elif level:
        # Map "Low", "Mid", "High" dari frontend (MVP) ke "LOTS", "MOTS", "HOTS"
        level_upper = level.upper()
        mapping = {
            "LOW": "LOTS",
            "MID": "MOTS",
            "HIGH": "HOTS"
        }
        internal_level = mapping.get(level_upper, level_upper)

        lvl_data = registry.get(internal_level)
        if not lvl_data:
            log.warning(f"Level '{level}' not found in leveling configuration")
            return ""
        if is_assessment:
            return _compile_assessment_prose(lvl_data)
        else:
            return _compile_pedagogy_prose(task_type, lvl_data)
    else:
        return ""

def _normalize_subject_key(mata_pelajaran: str) -> str:
    if not mata_pelajaran: return ""
    key = str(mata_pelajaran).lower().strip()
    return key.replace(" ", "_")

def compile_subject_registry(task_type: str, mata_pelajaran: str) -> str:
    needs_stimulus = task_type in TASKS_WITH_STIMULUS
    
    if not needs_stimulus:
        if not mata_pelajaran: return ""
        return f"Mata pelajaran: {mata_pelajaran}"

    raw = _read(STIMULUS_FILE)
    if not raw: return ""
    stimulus_dict = _load_dict(raw)
    if not stimulus_dict: return ""

    key = _normalize_subject_key(mata_pelajaran)
    target_data = None
    
    if key in stimulus_dict:
        target_data = stimulus_dict[key]
    else:
        first_word = key.split("_")[0]
        if first_word in stimulus_dict:
            target_data = stimulus_dict[first_word]

    if not target_data:
        return ""

    lines = []
    guidance = target_data.get("guidance", "")
    if guidance:
        lines.append(guidance)

    formats = target_data.get("formats", [])
    if formats:
        formats_str = ", ".join(formats)
        lines.append(f"\nStimulus dapat menggunakan: {formats_str}.")

    return "\n".join(lines)
