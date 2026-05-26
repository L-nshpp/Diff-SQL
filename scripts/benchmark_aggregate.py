#!/usr/bin/env python3
import argparse
import json
import os
from collections import defaultdict


def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() == "true"
    if isinstance(v, (int, float)):
        return bool(v)
    return False


def r_ves_score(speedup):
    tau = safe_float(speedup, None)
    if tau is None:
        return None
    if tau >= 2:
        return 1.0
    if tau >= 1.2:
        return 0.75
    if tau >= 1:
        return 0.5
    if tau >= 0.5:
        return 0.25
    return 0.0


def normalize_dialect_name(v):
    s = str(v or "").strip().lower()
    if s in ("postgres", "postgresql"):
        return "postgres"
    return s or "unknown"


def detect_dialect_from_file(path):
    parent = os.path.basename(os.path.dirname(path))
    parent_norm = normalize_dialect_name(parent)
    if parent_norm != "unknown":
        return parent_norm

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                for k in ("eval_dialect", "sample_dialect", "dialect"):
                    v = normalize_dialect_name(r.get(k))
                    if v != "unknown":
                        return v
                break
    except Exception:
        pass
    return "unknown"


def collect_files(root_dir, dialects, file_pattern=None):
    files = []
    for d in dialects:
        ddir = os.path.join(root_dir, d)
        if not os.path.isdir(ddir):
            continue
        for name in sorted(os.listdir(ddir)):
            if name.endswith('.jsonl'):
                if file_pattern and file_pattern not in name:
                    continue
                files.append((d, os.path.join(ddir, name)))
    return files


def collect_explicit_files(paths):
    files = []
    for raw in paths:
        p = raw.strip()
        if not p:
            continue
        abs_path = p if os.path.isabs(p) else os.path.abspath(p)
        if not os.path.isfile(abs_path):
            continue
        files.append((detect_dialect_from_file(abs_path), abs_path))
    return files


def make_empty_stat():
    return {
        'processed': 0,
        'match': 0,
        'r_ves_sum': 0.0,
    }


def summarize(files, group_by='dialect'):
    by_group = defaultdict(make_empty_stat)

    for dialect, path in files:
        if group_by == 'file':
            group_key = os.path.basename(path)
        elif group_by == 'path':
            group_key = path
        else:
            group_key = dialect

        stat = by_group[group_key]
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue

                stat['processed'] += 1
                is_match = parse_bool(r.get('is_match', False))
                if is_match:
                    stat['match'] += 1
                    score = r_ves_score(r.get('speedup'))
                    if score is not None:
                        stat['r_ves_sum'] += score

    return by_group


def print_summary(by_group, group_by='dialect'):
    group_label = {
        'dialect': 'dialect',
        'file': 'file',
        'path': 'path',
    }.get(group_by, group_by)
    first_col_width = max(len(group_label), *(len(str(k)) for k in by_group.keys()), 12)
    header = (
        f"{group_label:<{first_col_width}} {'processed':>10} {'match':>8} "
        f"{'match_rate':>11} {'r_ves':>10}"
    )
    print(header)
    print('-' * len(header))

    total = {
        'processed': 0,
        'match': 0,
        'r_ves_sum': 0.0,
    }

    for group_name in sorted(by_group.keys()):
        s = by_group[group_name]
        processed = s['processed']
        match_rate = (s['match'] / processed * 100.0) if processed else 0.0
        r_ves = (s['r_ves_sum'] / processed) if processed else 0.0

        print(
            f"{group_name:<{first_col_width}} {processed:>10} {s['match']:>8} "
            f"{match_rate:>10.1f}% {r_ves:>10.4f}"
        )

        for k in total:
            total[k] += s[k]

    t_processed = total['processed']
    t_match_rate = (total['match'] / t_processed * 100.0) if t_processed else 0.0
    t_r_ves = (total['r_ves_sum'] / t_processed) if t_processed else 0.0

    print('-' * len(header))
    print(
        f"{'all':<12} {t_processed:>10} {total['match']:>8} "
        f"{t_match_rate:>10.1f}% {t_r_ves:>10.4f}"
    )


def main():
    parser = argparse.ArgumentParser(description='Aggregate benchmark eval jsonl outputs.')
    parser.add_argument('--root', default='outputs',
                        help='Root output directory (contains per-dialect subdirs).')
    parser.add_argument('--dialects', default='postgres',
                        help='Comma-separated dialect list to aggregate.')
    parser.add_argument('--file-pattern', default='',
                        help='Only include jsonl files whose filename contains this substring (e.g. 0331).')
    parser.add_argument('--file', default='',
                        help='Single jsonl file path, or multiple comma-separated paths. When set, --root/--dialects/--file-pattern are ignored.')
    parser.add_argument('--group-by', default='dialect', choices=['dialect', 'file', 'path'],
                        help='Aggregate by dialect, filename, or full path.')
    args = parser.parse_args()

    explicit_file = args.file.strip()
    if explicit_file:
        files = collect_explicit_files([x for x in explicit_file.split(',') if x.strip()])
        if not files:
            print(f'No valid jsonl file found from --file={explicit_file}')
            return
    else:
        dialects = [d.strip() for d in args.dialects.split(',') if d.strip()]
        file_pattern = args.file_pattern.strip() or None
        files = collect_files(args.root, dialects, file_pattern=file_pattern)
        if not files:
            suffix = f' with pattern={file_pattern}' if file_pattern else ''
            print(f'No output jsonl files found under {args.root} for {dialects}{suffix}')
            return

    by_group = summarize(files, group_by=args.group_by)
    print_summary(by_group, group_by=args.group_by)


if __name__ == '__main__':
    main()
