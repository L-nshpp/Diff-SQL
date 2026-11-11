from pathlib import Path

replacements = {
    "Correctness Aligner": "Correctness Aligner",
    "correctness aligner": "correctness aligner",
    "correctness-aligner": "correctness-aligner",
    "correctness_aligner": "correctness_aligner",
    "CorrectnessAligner": "CorrectnessAligner",
    "CORRECTNESS_ALIGNER": "CORRECTNESS_ALIGNER",
}

excluded = {".git", ".venv", "venv", "__pycache__", "node_modules"}

for path in Path(".").rglob("*"):
    if not path.is_file() or any(p in excluded for p in path.parts):
        continue

    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        continue

    updated = original
    for old, new in replacements.items():
        updated = updated.replace(old, new)

    if updated != original:
        path.write_text(updated, encoding="utf-8")
        print(f"Updated: {path}")
