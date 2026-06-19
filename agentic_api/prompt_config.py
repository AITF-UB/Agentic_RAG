import os
import ast
import json
import logging

log = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
LEVELING_CRITERIA_FILE = "leveling_criteria.md"
STIMULUS_FILE = "stimulus.md"

# ── Tasks yang membutuhkan stimulus configuration (assessment) ───────────────
TASKS_WITH_STIMULUS: set = {"quiz_pg", "quiz_essay", "pretest", "pilgan", "essay"}

# ── Tasks yang menggunakan semua 3 level sekaligus ───────────────────────────
TASKS_WITH_MIXED_LEVELS: set = {"pretest"}

# ── Mapping nama task dari graph.py ke nama PSR2 ─────────────────────────────
TASK_TYPE_ALIAS = {
    "bacaan": "materi",
    "quiz_pg": "pilgan",
    "quiz_essay": "essay",
    # pretest, flashcard, mindmap sudah sama
}


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


def _load_leveling_dict() -> dict:
    raw = _read(LEVELING_CRITERIA_FILE)
    if not raw:
        return {}
    return _load_dict(raw)


def _load_stimulus_dict() -> dict:
    raw = _read(STIMULUS_FILE)
    if not raw:
        return {}
    return _load_dict(raw)


# ── Teks alami ────────────────────────────────────────────────────────────────

def _join_natural(items: list, conjunction: str = "dan") -> str:
    """Gabungkan list kata dengan konjungsi alami Bahasa Indonesia."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"


def _compile_pedagogy_prose(task_type: str, level_data: dict) -> str:
    """
    Kompilasi konfigurasi level sebagai prose instruksional untuk task konten
    (materi, flashcard, mindmap). Tidak menyebutkan nama level secara eksplisit.
    """
    TASK_VERBS = {
        "materi": "Bangun materi",
        "bacaan": "Bangun materi",
        "flashcard": "Buat flashcard",
        "mindmap": "Susun mindmap",
    }

    kompetensi = level_data.get("kompetensi_inti", "")
    pedagogi = level_data.get("pedagogi", {})
    asesmen = level_data.get("asesmen", {})

    parts: list = []

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
    """
    Kompilasi konfigurasi level sebagai prose instruksional untuk task asesmen
    (quiz_pg/pilgan, quiz_essay/essay). Tidak menyebutkan nama level secara eksplisit.
    """
    asesmen = level_data.get("asesmen", {})

    parts: list = []

    operasi = asesmen.get("operasi_kognitif", [])
    if operasi:
        parts.append(
            f"Buat soal yang mengukur kemampuan siswa dalam {_join_natural(operasi)}."
        )

    target = asesmen.get("target_pengukuran", [])
    if target:
        parts.append(f"Sasaran pengukuran: {_join_natural(target)}.")

    hindari = asesmen.get("hindari", [])
    if hindari:
        parts.append(f"Hindari soal yang hanya menguji {_join_natural(hindari, 'atau')}.")

    return "\n\n".join(parts)


def _compile_pretest_level_prose(level_key: str, level_data: dict) -> str:
    """
    Kompilasi satu blok level untuk pretest (mixed-level task).
    Pretest menggunakan nama level (LOTS/MOTS/HOTS) karena distribusi soal
    secara eksplisit merujuk ke nama-nama tersebut.
    """
    asesmen = level_data.get("asesmen", {})

    lines: list = [f"{level_key}:"]

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


# ── Entry Points ──────────────────────────────────────────────────────────────

def compile_level_configuration(task_type: str, level: str = None) -> str:
    """
    Kompilasi konfigurasi leveling sebagai prose instruksional natural.

    - Task konten (materi/bacaan, flashcard, mindmap): prose pedagogis (tanpa nama level).
    - Task asesmen (quiz_pg/pilgan, quiz_essay/essay): prose asesmen (tanpa nama level).
    - Pretest (mixed): ketiga level dengan label LOTS/MOTS/HOTS.
    """
    registry = _load_leveling_dict()
    if not registry:
        return ""

    # Normalisasi task_type alias
    canonical_task = TASK_TYPE_ALIAS.get(task_type, task_type)

    is_mixed = canonical_task in TASKS_WITH_MIXED_LEVELS
    is_assessment = canonical_task in TASKS_WITH_STIMULUS

    if is_mixed:
        sections: list = []
        for lvl_key in ["LOTS", "MOTS", "HOTS"]:
            lvl_data = registry.get(lvl_key)
            if lvl_data:
                sections.append(_compile_pretest_level_prose(lvl_key, lvl_data))
        return "\n\n".join(sections)

    # Normalisasi nama level: support LOTS/MOTS/HOTS dan Low/Mid/High (legacy)
    LEVEL_ALIAS = {
        "low": "LOTS", "Low": "LOTS", "LOW": "LOTS",
        "mid": "MOTS", "Mid": "MOTS", "MID": "MOTS",
        "high": "HOTS", "High": "HOTS", "HIGH": "HOTS",
    }
    canonical_level = LEVEL_ALIAS.get(level, level) if level else None

    if canonical_level:
        lvl_data = registry.get(canonical_level)
        if not lvl_data:
            log.warning("Level '%s' tidak ditemukan dalam leveling configuration", canonical_level)
            return ""
        if is_assessment:
            return _compile_assessment_prose(lvl_data)
        else:
            return _compile_pedagogy_prose(canonical_task, lvl_data)

    return ""


def compile_stimulus_configuration(mata_pelajaran: str) -> str:
    """
    Kompilasi konfigurasi stimulus sebagai prose natural untuk task asesmen.
    Menghasilkan guidance + format stimulus yang tersedia untuk mapel tertentu.
    """
    stimulus_dict = _load_stimulus_dict()
    if not stimulus_dict:
        return ""

    # Normalisasi kunci mapel
    key = mata_pelajaran.lower().strip().replace(" ", "_")
    target_data = None

    if key in stimulus_dict:
        target_data = stimulus_dict[key]
    else:
        first_word = key.split("_")[0]
        if first_word in stimulus_dict:
            target_data = stimulus_dict[first_word]

    if not target_data:
        log.warning("Tidak ada stimulus entry untuk '%s'.", mata_pelajaran)
        return ""

    lines: list = []

    guidance = target_data.get("guidance", "")
    if guidance:
        lines.append(guidance)

    formats = target_data.get("formats", [])
    if formats:
        formats_str = ", ".join(formats)
        lines.append(f"\nStimulus dapat menggunakan: {formats_str}.")

    return "\n".join(lines)


def compile_subject_configuration(mata_pelajaran: str) -> str:
    """
    Kompilasi konfigurasi mata pelajaran sederhana untuk task konten (materi).
    """
    if not mata_pelajaran:
        return ""
    return f"Mata pelajaran: {mata_pelajaran}"


# ── Fungsi Legacy (backward compatible) ──────────────────────────────────────
# Agar graph.py tidak perlu diubah namanya, fungsi lama tetap tersedia
# sebagai wrapper ke implementasi baru.

def compile_leveling_registry(task_type: str, level: str = None) -> str:
    """Legacy wrapper → compile_level_configuration."""
    return compile_level_configuration(task_type, level)


def compile_subject_registry(task_type: str, mata_pelajaran: str) -> str:
    """
    Legacy wrapper. Memilih antara stimulus config (assessment) atau
    subject config (konten) berdasarkan task_type.
    """
    canonical_task = TASK_TYPE_ALIAS.get(task_type, task_type)
    if canonical_task in TASKS_WITH_STIMULUS:
        return compile_stimulus_configuration(mata_pelajaran)
    else:
        return compile_subject_configuration(mata_pelajaran)
