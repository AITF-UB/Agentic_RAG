"""
Prompt builder — loads prompts from disk and fills placeholders.

Each prompt template lives in its own .md file under `instrcution_bahasa_indonesia/`.
This module reads them at runtime so you can edit prompts without touching code.

Architecture (New Bahasa Indonesia Instructions):
  SYSTEM PROMPT
  │
  ├── LEVELING_CONFIGURATION   → compiled as text per level
  │
  ├── STIMULUS_CONFIGURATION   → compiled as text per subject (assessment only)
  │
  └── TASK PROMPTS
        ├── materi      (level ✅, stimulus ❌)
        ├── flashcard   (level ✅, stimulus ❌)
        ├── mindmap     (level ✅, stimulus ❌)
        ├── pilgan      (level ✅, stimulus ✅)
        ├── pretest     (mixed LOTS/MOTS/HOTS, stimulus ✅)
        └── essay       (level ✅, stimulus ✅)

Compilation rules:
  - Don't send raw registry dicts — compile into human-readable text.
  - Leveling: extract target level's fields, render as text block.
  - Stimulus: extract subject's guidance + formats, render as text block.
  - Pretest is special: compiles ALL 3 levels into one block.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

# pyrefly: ignore [missing-import]
from src.config import (
    CHARS_PER_TOKEN,
    LEVELING_CRITERIA_FILE,
    MAX_SEQ_LENGTH,
    PROMPTS_DIR,
    RESERVED_RESPONSE_TOKENS,
    SYSTEM_PROMPT_FILE,
    TASK_PROMPT_FILES,
)

STIMULUS_FILE: str = "stimulus_profile.md"

log = logging.getLogger(__name__)

# ── Orchestration Table ──────────────────────────────────────────────
# Which tasks need stimulus injection (assessment tasks only)
TASKS_WITH_STIMULUS: set[str] = {"pilgan", "pretest", "essay"}

# Which task uses mixed (all 3) levels instead of single level
TASKS_WITH_MIXED_LEVELS: set[str] = {"pretest"}


# ── File I/O ─────────────────────────────────────────────────────────

def _read(filename: str) -> str:
    """Read a prompt file from PROMPTS_DIR, strip trailing whitespace."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_system_prompt() -> str:
    """Return the full system prompt text."""
    return _read(SYSTEM_PROMPT_FILE)


# ── Registry Loaders ─────────────────────────────────────────────────

def _parse_dict_file(filename: str) -> dict:
    """Parse a .md file containing a Python dict literal (e.g. LEVELING_CONFIGURATION = {...})."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        log.warning("Dict file not found: %s", path)
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    try:
        brace_idx = raw.find("{")
        if brace_idx > 0:
            raw = raw[brace_idx:]
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        log.warning("Failed to parse %s as Python dict", filename)
        return {}


def _load_leveling_dict() -> dict:
    """Parse the leveling criteria file as a Python dict literal."""
    return _parse_dict_file(LEVELING_CRITERIA_FILE)


def _load_stimulus_dict() -> dict:
    """Parse the stimulus profile file as a Python dict literal."""
    return _parse_dict_file(STIMULUS_FILE)


# ── Text Compilation ─────────────────────────────────────────────────

def _join_natural(items: list[str], conjunction: str = "dan") -> str:
    """Join a list of items with natural language connectors.

    Examples:
      ["a"]             → "a"
      ["a", "b"]        → "a dan b"
      ["a", "b", "c"]   → "a, b, dan c"
    """
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"


def _compile_pedagogy_prose(task_type: str, level_data: dict) -> str:
    """
    Compile level config as pedagogical instruction prose for non-assessment tasks.

    Produces natural directives like:
      "Bangun materi yang mendorong siswa menggunakan pengetahuan
       untuk menganalisis situasi dan memecahkan masalah..."

    No level names, labels, or structural keys are exposed.
    """
    TASK_VERBS = {
        "materi": "Bangun materi",
        "flashcard": "Buat flashcard",
        "mindmap": "Susun mindmap",
    }

    kompetensi = level_data.get("kompetensi_inti", "")
    pedagogi = level_data.get("pedagogi", {})
    asesmen = level_data.get("asesmen", {})

    parts: list[str] = []

    # Opening instruction: task verb + kompetensi as directive
    verb = TASK_VERBS.get(task_type, "Buat konten")
    if kompetensi:
        k = kompetensi[0].lower() + kompetensi[1:].rstrip(".")
        parts.append(f"{verb} yang mendorong siswa {k}.")

    # Focus areas from pedagogi
    fokus = pedagogi.get("fokus_pembelajaran", [])
    if fokus:
        parts.append(f"Fokuskan pembahasan pada {_join_natural(fokus)}.")

    # Anti-patterns from asesmen block (adapted for content context)
    hindari_raw = asesmen.get("hindari", [])
    if hindari_raw:
        # Filter out question-specific phrasing that doesn't apply to content tasks
        hindari = [item for item in hindari_raw if "pertanyaan" not in item.lower()]
        if not hindari:
            hindari = ["hafalan tanpa konteks"]
        parts.append(f"Hindari {_join_natural(hindari, 'atau')}.")

    return "\n\n".join(parts)


def _compile_assessment_prose(level_data: dict) -> str:
    """
    Compile level config as assessment instruction prose for pilgan/essay.

    Produces natural directives like:
      "Buat soal yang mengukur kemampuan siswa dalam penerapan,
       interpretasi, perbandingan, dan analisis kontekstual."

    No level names, labels, or structural keys are exposed.
    """
    asesmen = level_data.get("asesmen", {})

    parts: list[str] = []

    # Opening from cognitive operations
    operasi = asesmen.get("operasi_kognitif", [])
    if operasi:
        parts.append(
            f"Buat soal yang mengukur kemampuan siswa dalam {_join_natural(operasi)}."
        )

    # Measurement targets
    target = asesmen.get("target_pengukuran", [])
    if target:
        parts.append(f"Sasaran pengukuran: {_join_natural(target)}.")

    # Anti-patterns
    hindari = asesmen.get("hindari", [])
    if hindari:
        parts.append(f"Hindari soal yang hanya menguji {_join_natural(hindari, 'atau')}.")

    return "\n\n".join(parts)


def _compile_pretest_level_prose(level_key: str, level_data: dict) -> str:
    """
    Compile a single level block for pretest (mixed-level task).

    Pretest DOES use level names (LOTS/MOTS/HOTS) because the distribution
    section explicitly references them (e.g. "4 soal LOTS, 3 soal MOTS").
    """
    asesmen = level_data.get("asesmen", {})

    lines: list[str] = [f"{level_key}:"]

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


def compile_level_configuration(
    task_type: str,
    level: str | None = None,
) -> str:
    """
    Compile leveling configuration as natural instructional prose.

    - For single-level non-assessment tasks: pedagogical directives (no level name).
    - For single-level assessment tasks: assessment design directives (no level name).
    - For pretest (mixed): all 3 levels with labels (needed for distribution mapping).
    """
    registry = _load_leveling_dict()
    if not registry:
        return ""

    is_assessment = task_type in TASKS_WITH_STIMULUS
    is_mixed = task_type in TASKS_WITH_MIXED_LEVELS

    if is_mixed:
        # Pretest: compile all 3 levels with labels
        sections: list[str] = []
        for lvl_key in ["LOTS", "MOTS", "HOTS"]:
            lvl_data = registry.get(lvl_key)
            if lvl_data:
                sections.append(_compile_pretest_level_prose(lvl_key, lvl_data))
        return "\n\n".join(sections)
    elif level:
        # Single level
        lvl_data = registry.get(level)
        if not lvl_data:
            log.warning("Level '%s' not found in leveling configuration", level)
            return ""
        if is_assessment:
            return _compile_assessment_prose(lvl_data)
        else:
            return _compile_pedagogy_prose(task_type, lvl_data)
    else:
        return ""


def compile_stimulus_configuration(mata_pelajaran: str) -> str:
    """
    Compile stimulus configuration as human-readable text for assessment tasks.

    Extracts the subject's 'guidance' and 'formats' from STIMULUS_CONFIGURATION
    and renders them as a readable block.
    """
    stimulus_dict = _load_stimulus_dict()
    if not stimulus_dict:
        return ""

    # Normalize subject key
    key = _normalize_subject_key(mata_pelajaran)

    # Try exact match, then first word
    target_data = None
    if key in stimulus_dict:
        target_data = stimulus_dict[key]
    else:
        first_word = key.split("_")[0]
        if first_word in stimulus_dict:
            target_data = stimulus_dict[first_word]

    if not target_data:
        log.warning(
            "No stimulus entry for '%s' (tried: '%s', '%s'). Using empty.",
            mata_pelajaran, key, key.split("_")[0] if key else "",
        )
        return ""

    lines: list[str] = []

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
    Compile a minimal subject configuration for the materi template.

    The [KONFIGURASI_MATA_PELAJARAN] section in materi.md expects
    subject context. We provide a brief identifier since there's
    no dedicated subject configuration registry.
    """
    if not mata_pelajaran:
        return ""
    return f"Mata pelajaran: {mata_pelajaran}"


def _normalize_subject_key(mata_pelajaran: str) -> str:
    """
    Normalize mata_pelajaran to a stimulus key.

    Examples:
      'Matematika Umum' → 'matematika_umum'
      'Bahasa Indonesia' → 'bahasa_indonesia'
      'IPS' → 'ips'
      'Matematika' → 'matematika'
    """
    key = mata_pelajaran.lower().strip()
    full_key = key.replace(" ", "_")
    return full_key


# ── Token Budget ──────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length using CHARS_PER_TOKEN ratio."""
    return int(len(text) / CHARS_PER_TOKEN)


def _truncate_to_budget(
    chunks_text: str,
    fixed_chars: int,
    sub_bab: str = "",
) -> str:
    """
    Truncate chunks_text so the total SFT sample fits within MAX_SEQ_LENGTH.

    Token budget breakdown:
      MAX_SEQ_LENGTH = system_prompt + user_prompt + assistant_response
                     = fixed_parts + chunks_text + RESERVED_RESPONSE_TOKENS

    If chunks_text fits within the remaining budget, it is returned unchanged.
    If it exceeds the budget, it is truncated at the last sentence boundary
    (period followed by space) and a [TRUNCATED] marker is appended.

    Parameters
    ----------
    chunks_text : str
        The raw chunk content to potentially truncate.
    fixed_chars : int
        Character count of all non-chunk parts (system + template + header + criteria).
    sub_bab : str
        Used for logging when truncation happens.
    """
    if not chunks_text:
        return chunks_text

    # Calculate remaining character budget for chunks
    fixed_tokens = int(fixed_chars / CHARS_PER_TOKEN)
    remaining_tokens = MAX_SEQ_LENGTH - RESERVED_RESPONSE_TOKENS - fixed_tokens

    if remaining_tokens <= 0:
        log.warning(
            "[TokenBudget] No room for chunks in '%s'. "
            "Fixed parts already use %d tokens (budget: %d - %d reserved).",
            sub_bab, fixed_tokens, MAX_SEQ_LENGTH, RESERVED_RESPONSE_TOKENS,
        )
        return ""

    max_chunk_chars = int(remaining_tokens * CHARS_PER_TOKEN)

    if len(chunks_text) <= max_chunk_chars:
        return chunks_text

    # Truncate at last sentence boundary
    truncated = chunks_text[:max_chunk_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chunk_chars * 0.5:  # only cut at sentence if >50% kept
        truncated = truncated[: last_period + 1]

    original_tok = _estimate_tokens(chunks_text)
    truncated_tok = _estimate_tokens(truncated)
    log.warning(
        "[TokenBudget] Truncated chunks for '%s': %d → %d tokens (-%d tok, budget: %d tok)",
        sub_bab, original_tok, truncated_tok,
        original_tok - truncated_tok, remaining_tokens,
    )

    return truncated + "\n[TRUNCATED]"


# ── Prompt Assembly ───────────────────────────────────────────────────

def build_user_prompt(
    task_type: str,
    metadata: dict,
    level: str | None = None,
) -> str:
    """
    Build a complete user prompt for a given task.

    Orchestration flow:
      1. Load the raw prompt template from disk.
      2. Compile leveling configuration as text for the target level.
      3. Compile stimulus configuration as text (assessment tasks only).
      4. Inject chunk content as [KONTEKS_PEMBELAJARAN].
      5. Fill in all placeholders.
      6. Truncate chunks if total exceeds SFT token budget.

    Parameters
    ----------
    task_type : str
        One of: materi, flashcard, mindmap, pilgan, essay, pretest
    metadata : dict
        A single sub_bab entry from the chunk JSON (with chunks_text).
    level : str | None
        LOTS / MOTS / HOTS. None for pretest (uses mixed levels internally).
    """
    filename = TASK_PROMPT_FILES.get(task_type)
    if not filename:
        raise ValueError(f"Unknown task type: {task_type}")

    template = _read(filename)
    system_prompt_text = load_system_prompt()

    mata_pelajaran = metadata.get("mata_pelajaran", "")

    # ── STEP 2: Compile configurations as text ──

    # Level configuration (all tasks use leveling)
    level_text = compile_level_configuration(task_type, level)

    # Stimulus configuration (assessment tasks only)
    needs_stimulus = task_type in TASKS_WITH_STIMULUS
    stimulus_text = compile_stimulus_configuration(mata_pelajaran) if needs_stimulus else ""

    # Subject configuration (for materi template's {SUBJECT_CONFIGURATION})
    subject_text = compile_subject_configuration(mata_pelajaran)

    # ATP text from the chunk metadata (may be empty)
    atp_text = metadata.get("atp", "").strip()
    atp_block = atp_text if atp_text else "ATP tidak tersedia untuk sub-bab ini."

    # ── Minimal identity header ──
    header = (
        f"Mapel: {metadata.get('mata_pelajaran', '')} | "
        f"Bab: {metadata.get('bab_judul', '')} | "
        f"Sub Bab: {metadata.get('sub_bab', '')}"
    )
    if level:
        header += f" | Target: {level}"

    # ── Calculate fixed-part character count for token budget ──
    fixed_chars = (
        len(system_prompt_text)
        + len(template)
        + len(header)
        + len(level_text)
        + len(stimulus_text)
        + len(subject_text)
        + len(atp_block)
    )

    # ── Truncate chunks to fit within SFT token budget ──
    chunks_text = metadata.get("chunks_text", "")
    chunks_text = _truncate_to_budget(
        chunks_text,
        fixed_chars,
        sub_bab=metadata.get("sub_bab", ""),
    )

    # ── Assemble context block ──
    context_parts = [header]

    if chunks_text:
        context_parts.append(f"\n--- MATERI ---\n{chunks_text}")

    context_block = "\n".join(context_parts)

    # ── STEP 4: Fill template placeholders ──
    prompt = template

    # Level configuration — templates use either {LEVEL_CONFIGURATION} or
    # {COMPILED_LEVEL_CONFIGURATION} (pretest uses the latter)
    prompt = prompt.replace("{LEVEL_CONFIGURATION}", level_text)
    prompt = prompt.replace("{COMPILED_LEVEL_CONFIGURATION}", level_text)

    # Stimulus configuration (will be empty string for non-assessment tasks,
    # so if the placeholder isn't in the template, nothing happens)
    prompt = prompt.replace("{STIMULUS_CONFIGURATION}", stimulus_text)

    # Subject configuration (used by materi template)
    prompt = prompt.replace("{SUBJECT_CONFIGURATION}", subject_text)

    # ATP injection
    prompt = prompt.replace("{atp}", atp_block)

    # Context injection
    prompt = prompt.replace("{context}", context_block)

    return prompt
