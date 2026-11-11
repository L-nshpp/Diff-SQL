
from pathlib import Path

replacements = {
    "constraint_aligner": "correctness_aligner",
    "constraint-aligner": "correctness-aligner",
    "ConstraintAligner": "CorrectnessAligner",
    "Constraint_Aligner": "Correctness_Aligner",
    "Constraint-Aligner": "Correctness-Aligner",
    "CONSTRAINT_ALIGNER": "CORRECTNESS_ALIGNER",
}

excluded = {".git", ".venv", "venv", "__pycache__", "node_modules"}

root = Path(".")
renamed = 0

# 从最深层开始，避免先重命名父目录导致子路径失效
paths = sorted(
    (p for p in root.rglob("*")
     if not any(part in excluded for part in p.parts)),
    key=lambda p: len(p.parts),
    reverse=True
)

for path in paths:
    new_name = path.name

    for old, new in replacements.items():
        new_name = new_name.replace(old, new)

    if new_name == path.name:
        continue

    new_path = path.with_name(new_name)

    if new_path.exists():
        print(f"SKIP (target exists): {new_path}")
        continue

    path.rename(new_path)
    print(f"RENAMED: {path} -> {new_path}")
    renamed += 1

print(f"\nTotal renamed: {renamed}")

