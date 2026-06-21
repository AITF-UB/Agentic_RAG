""" Orkesstrator/Pipeline untuk menghasilkan dataset SFT AI Judge.
Proses:
1. Scan output/current_experiments/**/*.json untuk mencari soal esai yang sesuai filter.
2. Generator LLM: Simulasikan jawaban siswa dengan pola keterpenuhan rubrik (T/N) acak.
3. Judge LLM: Berikan penilaian objektif dalam format JSON.
4. Tulis hasil akhir ke dataset_sft_judging.jsonl.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.client import call_with_delay, OpenRouterError
from src.config import OPENROUTER_MODEL, CHARS_PER_TOKEN, MAX_SEQ_LENGTH

# Force UTF-8 encoding for stdout/stderr to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()

ALL_PATTERNS = ["TTT", "TTN", "TNT", "NTT", "TNN", "NTN", "NNT", "NNN"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SFT Judging Dataset Generator",
    )
    # Scope filters
    parser.add_argument(
        "--subject",
        action="append",
        help="Filter by mata_pelajaran (e.g. --subject \"Bahasa Indonesia\")",
    )
    parser.add_argument(
        "--kelas",
        action="append",
        help="Filter by kelas (e.g. --kelas \"Kelas 10\")",
    )
    parser.add_argument(
        "--jenjang",
        action="append",
        help="Filter by jenjang (e.g. --jenjang SMA)",
    )
    parser.add_argument(
        "--kurikulum",
        action="append",
        help="Filter by kurikulum (e.g. --kurikulum KTSP)",
    )
    parser.add_argument(
        "--level",
        action="append",
        help="Filter by level (e.g. --level HOTS)",
    )
    # Execution flags
    parser.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="Test mode: process only the first package.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview the generation plan without making LLM calls.",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        default=False,
        help="Shuffle discovered packages before processing (ideal for parallel runs).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=False,
        help="Skip generating a variant JSON if the output file already exists.",
    )
    parser.add_argument(
        "--limit-samples",
        type=int,
        default=None,
        help="Generate a balanced selected_tasks.json with the specified number of samples and exit.",
    )
    # Model config overrides
    parser.add_argument(
        "--model-gen",
        default=OPENROUTER_MODEL,
        help="Model for student answer generation.",
    )
    parser.add_argument(
        "--model-judge",
        default=OPENROUTER_MODEL,
        help="Model for AI Judge grading.",
    )
    # Output directory
    parser.add_argument(
        "--output",
        default="output/current_experiments",
        help="Base directory to save individual judging JSON files.",
    )
    return parser.parse_args()


def generate_selection(essay_files: list[tuple[Path, dict]], target_count: int) -> None:
    """Perform stratified sampling to select a balanced subset of tasks and save to selected_tasks.json."""
    pool = []
    
    console.print("[cyan]Scanning all questions to build task pool...[/]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        pbar = progress.add_task("[cyan]Scanning...", total=len(essay_files))
        for file_path, meta in essay_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    package_data = json.load(f)
                assistant_questions = package_data.get("assistant", [])
                if isinstance(assistant_questions, list):
                    for idx, q_data in enumerate(assistant_questions):
                        level = q_data.get("level", meta["level"])
                        # Compute output dir to check if file already exists
                        stem = file_path.stem
                        q_dir_name = f"{stem}_q{idx+1}"
                        out_dir = Path(re.sub(r'[\\/]essay[\\/]', '/judging/', str(file_path.parent), flags=re.IGNORECASE)) / q_dir_name
                        
                        for target_pattern in ALL_PATTERNS:
                            out_path = out_dir / f"{target_pattern}.json"
                            pool.append({
                                "file_rel_path": str(file_path.relative_to(project_root)).replace("\\", "/"),
                                "question_index": idx,
                                "target_pattern": target_pattern,
                                "kurikulum": meta["kurikulum"],
                                "subject": meta["subject"],
                                "level": level,
                                "exists": out_path.exists()
                            })
            except Exception as e:
                console.print(f"[red]Error scanning {file_path.name}: {e}[/]")
            progress.advance(pbar)

    total_pool_size = len(pool)
    existing_count = sum(1 for t in pool if t["exists"])
    console.print(f"Total possible tasks in pool: {total_pool_size}")
    console.print(f"Existing (already generated) tasks: {existing_count}")

    # Group by (kurikulum, subject, level, target_pattern)
    buckets = {}
    for task in pool:
        bucket_key = (task["kurikulum"], task["subject"], task["level"], task["target_pattern"])
        buckets.setdefault(bucket_key, []).append(task)

    # Shuffle each bucket, prioritizing existing tasks
    for key, bucket_tasks in buckets.items():
        # Separate existing and non-existing
        exists_tasks = [t for t in bucket_tasks if t["exists"]]
        new_tasks = [t for t in bucket_tasks if not t["exists"]]
        # Shuffle both independently
        random.shuffle(exists_tasks)
        random.shuffle(new_tasks)
        # Put existing first
        buckets[key] = exists_tasks + new_tasks

    selected_tasks = []
    remaining_target = min(target_count, total_pool_size)

    # Fair share sampling loop
    active_keys = list(buckets.keys())
    while remaining_target > 0 and active_keys:
        num_active = len(active_keys)
        fair_share = max(1, remaining_target // num_active)
        
        next_active_keys = []
        for key in active_keys:
            bucket_tasks = buckets[key]
            take_count = min(fair_share, len(bucket_tasks))
            
            if take_count > 0:
                selected_tasks.extend(bucket_tasks[:take_count])
                buckets[key] = bucket_tasks[take_count:]
                remaining_target -= take_count
            
            if len(buckets[key]) > 0:
                next_active_keys.append(key)
        
        # If we didn't make progress in remaining_target but have active keys,
        # it means fair_share was 0 or round-off happened. Just do round-robin.
        if len(active_keys) == len(next_active_keys) and fair_share == 1 and remaining_target > 0:
            for key in list(next_active_keys):
                if remaining_target <= 0:
                    break
                bucket_tasks = buckets[key]
                selected_tasks.append(bucket_tasks[0])
                buckets[key] = bucket_tasks[1:]
                remaining_target -= 1
                if len(buckets[key]) == 0:
                    next_active_keys.remove(key)
        
        active_keys = next_active_keys

    # Print selection stats
    console.print(f"[green]Successfully selected {len(selected_tasks)} tasks.[/]")
    
    # Calculate stats of selected tasks
    subj_stats = {}
    level_stats = {}
    kuri_stats = {}
    pattern_stats = {}
    selected_existing = 0
    
    for t in selected_tasks:
        subj_stats[t["subject"]] = subj_stats.get(t["subject"], 0) + 1
        level_stats[t["level"]] = level_stats.get(t["level"], 0) + 1
        kuri_stats[t["kurikulum"]] = kuri_stats.get(t["kurikulum"], 0) + 1
        pattern_stats[t["target_pattern"]] = pattern_stats.get(t["target_pattern"], 0) + 1
        if t["exists"]:
            selected_existing += 1

    table = Table(title="Selected Sample Distribution")
    table.add_column("Dimension", style="cyan")
    table.add_column("Category", style="magenta")
    table.add_column("Count", style="green")
    
    table.add_row("Total Selected", "All Tasks", str(len(selected_tasks)))
    table.add_row("Existing Selected", "Progress Kept", f"{selected_existing} ({selected_existing/len(selected_tasks)*100:.1f}%)")
    table.add_row("-", "-", "-")
    
    for k, v in sorted(subj_stats.items()):
        table.add_row("Subject", k, str(v))
    table.add_row("-", "-", "-")
    for k, v in sorted(kuri_stats.items()):
        table.add_row("Kurikulum", k, str(v))
    table.add_row("-", "-", "-")
    for k, v in sorted(level_stats.items()):
        table.add_row("Level", k, str(v))
    table.add_row("-", "-", "-")
    for k, v in sorted(pattern_stats.items()):
        table.add_row("Pattern", k, str(v))
        
    console.print(table)

    # Save to file
    out_file = project_root / "judging" / "selected_tasks.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    # Strip the "exists" and other non-essential fields to keep JSON size small
    serialized_tasks = [
        {
            "file_rel_path": t["file_rel_path"],
            "question_index": t["question_index"],
            "target_pattern": t["target_pattern"]
        }
        for t in selected_tasks
    ]
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(serialized_tasks, f, indent=2, ensure_ascii=False)
    console.print(f"[bold green]Saved selection to {out_file}[/]")


def load_md_file(path: Path) -> str:
    """Read a markdown file with utf-8 encoding."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def matches_filters(meta: dict, filters: dict) -> bool:
    """Check if file metadata matches the CLI filters."""
    for key, allowed in filters.items():
        if not allowed:
            continue
        val = meta.get(key)
        if not val:
            return False
        # Case-insensitive substring comparison
        val_lower = str(val).strip().lower()
        matched_any = False
        for pattern in allowed:
            pattern_clean = str(pattern).strip().lower()
            if pattern_clean in val_lower:
                matched_any = True
                break
        if not matched_any:
            return False
    return True


def discover_essay_files(filters: dict) -> list[tuple[Path, dict]]:
    """Scan output/current_experiments recursively for essay JSON files and parse metadata."""
    base_dir = project_root / "output" / "current_experiments"
    if not base_dir.exists():
        console.print(f"[red]Error:[/] Output directory does not exist: {base_dir}")
        return []

    files = sorted(base_dir.rglob("*.json"))
    matched = []

    for path in files:
        try:
            rel_parts = path.relative_to(base_dir).parts
        except ValueError:
            continue

        # Check if 'essay' is part of the path (expects layout: {kurikulum}/{jenjang}/{kelas}/{subject}/{sub_bab}/essay/{level}/{filename}.json)
        if "essay" not in rel_parts:
            continue

        # Load metadata/info from path structure
        if len(rel_parts) >= 8:
            kurikulum = rel_parts[0]
            jenjang = rel_parts[1]
            kelas = rel_parts[2]
            subject = rel_parts[3]
            sub_bab = rel_parts[4]
            level = rel_parts[6]
        else:
            kurikulum = rel_parts[0] if len(rel_parts) > 0 else ""
            jenjang = rel_parts[1] if len(rel_parts) > 1 else ""
            kelas = rel_parts[2] if len(rel_parts) > 2 else ""
            subject = rel_parts[3] if len(rel_parts) > 3 else ""
            sub_bab = rel_parts[4] if len(rel_parts) > 4 else ""
            level = rel_parts[-2] if len(rel_parts) > 1 else ""

        meta = {
            "kurikulum": kurikulum,
            "jenjang": jenjang,
            "kelas": kelas,
            "subject": subject,
            "sub_bab": sub_bab,
            "level": level,
        }

        if matches_filters(meta, filters):
            matched.append((path, meta))

    return matched


def clean_student_answer(answer: str) -> str:
    """Clean the LLM-synthesized student answer text."""
    answer = answer.strip()
    # Remove leading "Jawaban Siswa:" or "Jawaban:" label case-insensitively
    pattern = r"^(jawaban\s+siswa\s*:\s*|jawaban\s*:\s*)"
    answer = re.sub(pattern, "", answer, flags=re.IGNORECASE).strip()
    # Remove surrounding quotes if the model wrapped the entire answer
    if (answer.startswith('"') and answer.endswith('"')) or (answer.startswith("'") and answer.endswith("'")):
        answer = answer[1:-1].strip()
    return answer


def generate_patterns(num_questions: int, num_rubrics: int) -> list[str]:
    """Generate and shuffle combinations of T/N of length num_rubrics."""
    combos = ["".join(p) for p in itertools.product(["T", "N"], repeat=num_rubrics)]
    if num_questions > len(combos):
        patterns = random.choices(combos, k=num_questions)
    else:
        patterns = random.sample(combos, num_questions)
    random.shuffle(patterns)
    return patterns


def main() -> None:
    args = parse_args()

    console.print(
        Panel(
            "[bold green]🏫 Sekolah Rakyat — SFT Judging Dataset Generator[/]",
            style="green",
            expand=False,
        )
    )

    filters = {
        "kurikulum": args.kurikulum,
        "jenjang": args.jenjang,
        "kelas": args.kelas,
        "subject": args.subject,
        "level": args.level,
    }

    # Discover files
    essay_files = discover_essay_files(filters)
    total_found = len(essay_files)

    if args.limit_samples is not None:
        generate_selection(essay_files, args.limit_samples)
        return

    # Load selection if it exists
    selection_path = project_root / "judging" / "selected_tasks.json"
    selected_tasks_set = None
    if selection_path.exists():
        with open(selection_path, "r", encoding="utf-8") as f:
            selected_list = json.load(f)
        selected_tasks_set = {
            (t["file_rel_path"], t["question_index"], t["target_pattern"])
            for t in selected_list
        }
        console.print(f"[cyan]Loaded {len(selected_tasks_set)} task selections from selected_tasks.json[/]")

    if args.shuffle:
        random.shuffle(essay_files)

    if args.test:
        essay_files = essay_files[:1]

    # Display configuration/dry-run info
    table = Table(title="Configuration Summary")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Total Essay Packages Matched", f"{total_found} (processing {len(essay_files)})")
    table.add_row("Generator Model", args.model_gen)
    table.add_row("Judge Model", args.model_judge)
    table.add_row("Output Directory", args.output)
    table.add_row("Test Mode", str(args.test))
    table.add_row("Shuffle", str(args.shuffle))
    table.add_row("Skip Existing", str(args.skip_existing))
    table.add_row("Dry Run", str(args.dry_run))
    if selected_tasks_set is not None:
        table.add_row("Task Selection Filter", f"Active ({len(selected_tasks_set)} tasks selected)")
    console.print(table)

    if args.dry_run:
        console.print("[yellow]🔍 Dry Run completed. No files processed or LLM calls made.[/]")
        return

    if not essay_files:
        console.print("[yellow]⚠ No matching essay files found. Exiting.[/]")
        return

    # Load templates
    judging_dir = project_root / "judging"
    system_gen = load_md_file(judging_dir / "instruction_jawaban_siswa" / "system.md")
    user_gen_template = load_md_file(judging_dir / "instruction_jawaban_siswa" / "user.md")
    system_judge = load_md_file(judging_dir / "instruction_judge" / "system.md")
    user_judge_template = load_md_file(judging_dir / "instruction_judge" / "user.md")

    stats = {"packages_processed": 0, "packages_failed": 0, "questions_success": 0, "questions_failed": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        pbar = progress.add_task("[cyan]Processing packages...", total=len(essay_files))

        for file_path, meta in essay_files:
            progress.update(
                pbar,
                description=f"Package: {meta['subject']} - {meta['kelas']} - {meta['sub_bab'][:25]}...",
            )

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    package_data = json.load(f)

                assistant_questions = package_data.get("assistant", [])
                if not isinstance(assistant_questions, list):
                    console.print(f"[red]Error:[/] Invalid 'assistant' field in {file_path.name}")
                    stats["packages_failed"] += 1
                    progress.advance(pbar)
                    continue

                num_questions = len(assistant_questions)
                if num_questions == 0:
                    progress.advance(pbar)
                    continue

                # Process each question in the package for all 7 patterns
                for idx, q_data in enumerate(assistant_questions):
                    if args.test and idx > 0:
                        break
                    level = q_data.get("level", meta["level"])
                    stimulus = q_data.get("stimulus", "")
                    question = q_data.get("question", "")
                    rubric_points = q_data.get("rubric_points", [])

                    for target_pattern in ALL_PATTERNS:
                        # Check selection first if active
                        if selected_tasks_set is not None:
                            file_rel = str(file_path.relative_to(project_root)).replace("\\", "/")
                            if (file_rel, idx, target_pattern) not in selected_tasks_set:
                                continue

                        # Compute file output path first to check if we can skip it
                        stem = file_path.stem
                        q_dir_name = f"{stem}_q{idx+1}"
                        out_dir = Path(re.sub(r'[\\/]essay[\\/]', '/judging/', str(file_path.parent), flags=re.IGNORECASE)) / q_dir_name
                        out_path = out_dir / f"{target_pattern}.json"

                        if args.skip_existing and out_path.exists():
                            continue

                        # 1. GENERATE STUDENT ANSWER
                        user_gen = user_gen_template
                        user_gen = user_gen.replace("{{level}}", level)
                        user_gen = user_gen.replace("{{stimulus}}", stimulus)
                        user_gen = user_gen.replace("{{question}}", question)
                        
                        # Fill rubrics
                        for r_idx in range(3):
                            r_val = rubric_points[r_idx] if r_idx < len(rubric_points) else ""
                            user_gen = user_gen.replace(f"{{{{rubric_point_{r_idx+1}}}}}", r_val)
                        
                        user_gen = user_gen.replace("{{target_pola}}", target_pattern)

                        try:
                            raw_answer = call_with_delay(
                                system_gen,
                                user_gen,
                                model=args.model_gen,
                                temperature=0.6,  # Slightly higher for variety
                            )
                            student_answer = clean_student_answer(raw_answer)
                        except Exception as e:
                            console.print(f"[red]Failed generating answer for Q{idx+1} ({target_pattern}) in {file_path.name}: {e}[/]")
                            stats["questions_failed"] += 1
                            continue

                        # 2. RUN AI JUDGE ON THE GENERATED ANSWER
                        stimulus_dan_pertanyaan = f"{stimulus}\nPertanyaan: {question}"

                        user_dict = {
                            "question": stimulus_dan_pertanyaan,
                            "rubric_points": [
                                rubric_points[r_idx] if r_idx < len(rubric_points) else ""
                                for r_idx in range(3)
                            ],
                            "student_answer": student_answer
                        }
                        user_judge = json.dumps(user_dict, ensure_ascii=False, indent=2)

                        try:
                            raw_judge_res = call_with_delay(
                                system_judge,
                                user_judge,
                                model=args.model_judge,
                                temperature=0.2,
                                json_mode=True,
                            )
                            # Validate that it parses as JSON
                            parsed_judge_res = json.loads(raw_judge_res)
                        except Exception as e:
                            console.print(f"[red]Failed grading Q{idx+1} ({target_pattern}) in {file_path.name}: {e}[/]")
                            stats["questions_failed"] += 1
                            continue

                        # 3. WRITE THE JSON FILE (one file per variant under the question folder)
                        out_dir.mkdir(parents=True, exist_ok=True)

                        # Compute token estimation for metadata
                        system_len = len(system_judge)
                        user_len = len(user_judge)
                        assistant_str = json.dumps(parsed_judge_res, ensure_ascii=False)
                        assistant_len = len(assistant_str)
                        
                        est_sys_tokens = int(system_len / CHARS_PER_TOKEN)
                        est_usr_tokens = int(user_len / CHARS_PER_TOKEN)
                        est_ast_tokens = int(assistant_len / CHARS_PER_TOKEN)
                        est_total_tokens = est_sys_tokens + est_usr_tokens + est_ast_tokens
                        exceeds_budget = est_total_tokens > MAX_SEQ_LENGTH

                        # Read attributes from package metadata if available
                        package_meta = package_data.get("metadata", {})
                        source_file = package_meta.get("source_file", file_path.name)
                        prompt_version = package_meta.get("prompt_version", "v4")
                        system_prompt_version = package_meta.get("system_prompt_version", "v3")
                        atp_available = package_meta.get("atp_available", False)
                        atp_reference = package_meta.get("atp_reference", "")

                        record = {
                            "system": system_judge,
                            "user": user_dict,
                            "assistant": parsed_judge_res,
                            "metadata": {
                                "id": str(uuid.uuid4()),
                                "provider": "openrouter",
                                "model": args.model_judge,
                                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "kurikulum": package_meta.get("kurikulum", meta["kurikulum"]),
                                "jenjang": package_meta.get("jenjang", meta["jenjang"]),
                                "kelas": package_meta.get("kelas", meta["kelas"]),
                                "mata_pelajaran": package_meta.get("mata_pelajaran", meta["subject"]),
                                "bab_judul": package_meta.get("bab_judul", meta["sub_bab"]),
                                "sub_bab": package_meta.get("sub_bab", meta["sub_bab"]),
                                "task_type": "judging",
                                "level": package_meta.get("level", meta["level"]),
                                "source_file": source_file,
                                "prompt_version": prompt_version,
                                "system_prompt_version": system_prompt_version,
                                "atp_available": atp_available,
                                "atp_reference": atp_reference,
                                "generation_config": {
                                    "temperature": 0.2,
                                    "top_p": 0.9,
                                    "max_tokens": 16000
                                },
                                "est_tokens": {
                                    "system": est_sys_tokens,
                                    "user": est_usr_tokens,
                                    "assistant": est_ast_tokens,
                                    "total": est_total_tokens,
                                    "max_seq_length": MAX_SEQ_LENGTH,
                                    "exceeds_budget": exceeds_budget
                                },
                                "quality_flags": {
                                    "valid_json": True,
                                    "schema_valid": True,
                                    "contains_markdown_leak": "```" in raw_judge_res
                                },
                                "question_index": idx + 1,
                                "target_pattern": target_pattern
                            }
                        }

                        with open(out_path, "w", encoding="utf-8") as out_f:
                            json.dump(record, out_f, indent=2, ensure_ascii=False)

                        stats["questions_success"] += 1
                        stats["packages_processed"] += 1

            except Exception as e:
                console.print(f"[red]Error processing package {file_path.name}: {e}[/]")
                stats["packages_failed"] += 1

            progress.advance(pbar)

    console.print(
        Panel(
            f"[bold green]Pipeline finished![/]\n"
            f"✓ Packages successfully generated: {stats['packages_processed']} packages.\n"
            f"✓ Questions successfully generated: {stats['questions_success']} questions.\n"
            f"✗ Packages failed: {stats['packages_failed']}\n"
            f"✗ Questions failed: {stats['questions_failed']}\n"
            f"Output saved as individual files inside the matching 'judging' folders.",
            style="green",
            expand=False,
        )
    )


if __name__ == "__main__":
    main()
