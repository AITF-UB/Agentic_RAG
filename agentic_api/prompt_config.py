import os
import ast
import json
import logging

log = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
LEVELING_CRITERIA_FILE = "leveling_criteria.md"
STIMULUS_FILE = "stimulus.md"

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

def compile_leveling_registry(task_type: str, level: str = None) -> str:
    if task_type == "flashcard":
        return "{}"

    raw = _read(LEVELING_CRITERIA_FILE)
    if not raw: return "{}"
    registry = _load_dict(raw)
    if not registry: return "{}"

    levels_to_process = [level.upper()] if level and level.upper() in registry else list(registry.keys())
    compiled_registry = {}

    # Rules mapped from SFT prompt_builder
    LEVEL_FIELDS_BY_TASK = {
        "quiz_pg": ["dominant_operations", "question_behavior", "preferred_question_patterns", "avoid_patterns", "reasoning_priority"],
        "pretest": ["dominant_operations", "question_behavior", "preferred_question_patterns", "avoid_patterns", "reasoning_priority"],
        "bacaan": ["dominant_operations", "reasoning_priority", "expected_reasoning", "instruction_style"],
        "mindmap": ["dominant_operations", "reasoning_priority"],
        "quiz_essay": ["dominant_operations", "question_behavior", "preferred_question_patterns", "avoid_patterns", "reasoning_priority", "expected_reasoning"],
    }

    keep_fields = LEVEL_FIELDS_BY_TASK.get(task_type)

    for lvl in levels_to_process:
        entry = registry.get(lvl)
        if not entry: continue

        compiled_entry = {}
        if "label" in entry:
            compiled_entry["label"] = entry["label"]

        gen_behavior = entry.get("generation_behavior", {})
        if gen_behavior:
            if keep_fields:
                compiled_entry["generation_behavior"] = {k: v for k, v in gen_behavior.items() if k in keep_fields}
            else:
                compiled_entry["generation_behavior"] = gen_behavior
        else:
            fallback_fields = ["reasoning_depth", "cognitive_focus", "question_behavior"]
            for field in (keep_fields or fallback_fields):
                if field in entry:
                    compiled_entry[field] = entry[field]

        compiled_registry[lvl] = compiled_entry

    return json.dumps(compiled_registry, ensure_ascii=False, indent=2)


def compile_subject_registry(task_type: str, mata_pelajaran: str) -> str:
    raw = _read(STIMULUS_FILE)
    if not raw: return "{}"
    rules = _load_dict(raw)
    if not rules: return "{}"

    full_key = mata_pelajaran.lower().strip().replace(" ", "_")
    
    target_key = None
    if full_key in rules:
        target_key = full_key
    else:
        first_word = full_key.split("_")[0]
        if first_word in rules:
            target_key = first_word

    if not target_key:
        return "{}"

    subject_entry = rules[target_key]
    if not isinstance(subject_entry, dict):
        return json.dumps({target_key: subject_entry}, ensure_ascii=False, indent=2)

    compiled_entry = {}

    SUBJECT_FIELDS_BY_TASK = {
        "quiz_pg": ["required_elements", "reasoning_space", "writing_rules"],
        "pretest": ["required_elements", "reasoning_space", "writing_rules"],
        "bacaan": ["allowed_contexts", "reasoning_space", "writing_rules"],
        "mindmap": ["required_elements", "reasoning_space", "writing_rules"],
        "quiz_essay": ["required_elements", "reasoning_space", "writing_rules"],
    }

    keep_fields = SUBJECT_FIELDS_BY_TASK.get(task_type, ["required_elements", "reasoning_space", "writing_rules"])

    for field in keep_fields:
        if field in subject_entry:
            compiled_entry[field] = subject_entry[field]

    return json.dumps({target_key: compiled_entry}, ensure_ascii=False, indent=2)
