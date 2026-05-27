import glob
import hashlib
import json
import os
import queue
import random
import re
import statistics
import threading
import time
from collections import defaultdict

import psycopg2
import sqlparse

WORKDIR = os.getenv("EVAL_WORKDIR", "/workspace")
INPUT_DIR = os.getenv("EVAL_INPUT_DIR", os.path.join(WORKDIR, "data", "benchmark", "effi-sql"))
INPUT_FILE = os.getenv("EVAL_INPUT_FILE", "").strip()
OUTPUT_DIR = os.getenv("EVAL_OUTPUT_DIR", os.path.join(WORKDIR, "outputs"))
FILTER_FILE = os.getenv("EVAL_FILTER_FILE", "")
DB_MAPPING_FILE = os.getenv("DB_MAPPING_FILE", os.path.join(WORKDIR, "configs", "db_mapping.json"))
TPCH_MAPPING_FILE = os.getenv("TPCH_MAPPING_FILE", os.path.join(WORKDIR, "configs", "tpch_mapping.json"))
TIMEOUT_SECONDS = int(os.getenv("EVAL_TIMEOUT_SECONDS", "300"))
NUM_RUNS = int(os.getenv("EVAL_NUM_RUNS", "3"))
EVAL_DIALECT = os.getenv("EVAL_DIALECT", "postgres").strip().lower()
LONG_RUNNING_THRESHOLD_MS = 1 * 60 * 1000
COMPARE_FETCH_BATCH_SIZE = int(os.getenv("EVAL_COMPARE_FETCH_BATCH_SIZE", "5000"))
MAX_COMPARE_ROWS = int(os.getenv("EVAL_MAX_COMPARE_ROWS", "500000"))  # 超过1M行不再报错
TPCH_WORKER_COUNT = 1
SMALL_DB_WORKER_COUNT = 2
SPLIT_WORKER_COUNT = TPCH_WORKER_COUNT + SMALL_DB_WORKER_COUNT

TPCH_CORE_TABLES = {
    "region", "nation", "part", "supplier",
    "partsupp", "customer", "orders", "lineitem"
}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def in_docker():
    return os.path.exists("/.dockerenv")


def normalize_benchmark_scale(raw_scale):
    scale = str(raw_scale or "").strip().lower()
    if scale in ("", "default", "base", "standard"):
        return "default"
    if scale in ("scale", "scaled"):
        return "scale"
    return "default"


def normalize_sql_mode(raw_mode):
    mode = str(raw_mode or "").strip().lower()
    if mode in ("", "patch", "diff", "step1", "step2"):
        return "patch"
    if mode in ("end2end", "sql", "full_sql"):
        return "end2end"
    return "patch"


def normalize_response_field(raw_field):
    field = str(raw_field or "").strip().lower()
    if field in ("", "prediction"):
        return "prediction"
    if field in ("raw_response", "raw"):
        return "raw_response"
    return "prediction"


def normalize_db_key(db_key):
    return str(db_key or "").strip().lower()


BENCHMARK_SCALE = normalize_benchmark_scale(os.getenv("BENCHMARK_SCALE", "scale"))
EVAL_SQL_MODE = normalize_sql_mode(os.getenv("EVAL_SQL_MODE", "patch"))
EVAL_RESPONSE_FIELD = normalize_response_field(os.getenv("EVAL_RESPONSE_FIELD", "prediction"))


def default_tpch_dataset():
    if BENCHMARK_SCALE == "scale":
        return "tpch_3g"
    return "tpch_01g"


def normalize_dialect(raw_dialect):
    """
    统一规范化 jsonl 里的 dialect 字段：
    - None / 空 / 缺失 => postgresql
    """
    if raw_dialect is None:
        return "postgresql"

    d = str(raw_dialect).strip().lower()
    if d in ("", "none", "null"):
        return "postgresql"
    if d in ("postgres", "postgresql"):
        return "postgresql"
    return d


def record_dialect(record):
    """
    从样本读取 dialect。
    按需求：dialect 为 null 时默认 postgresql。
    """
    if not isinstance(record, dict):
        return "postgresql"
    return normalize_dialect(record.get("dialect"))


def load_filter_keys(filter_file_path):
    filter_map = defaultdict(list)
    with open(filter_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line.strip())
                instance_id = data.get("instance_id")
                if instance_id is not None:
                    slow_sql_type = data.get("slow_sql_type", "")
                    slow_sql_file = data.get("slow_sql_file", "")
                    filter_map[str(instance_id)].append((str(slow_sql_type), str(slow_sql_file)))
            except json.JSONDecodeError:
                continue
    return dict(filter_map)


def should_keep_record(record, filter_map, instance_id_counts):
    instance_id = str(record.get("instance_id", ""))
    if instance_id not in filter_map:
        return False
    if instance_id_counts.get(instance_id, 0) <= 1:
        return True

    record_type = str(record.get("slow_sql_type", ""))
    record_file = str(record.get("slow_sql_file", ""))
    for filter_type, filter_file in filter_map[instance_id]:
        if filter_type and record_type == filter_type:
            return True
        if filter_file and record_file == filter_file:
            return True
    return False


def restore_sql_from_prediction(base_sql, prediction):
    """
    patch 提取：只取第一个 diff 块，不合并、不尝试多个候选。
    找到第一个 diff 块后无论成功失败直接返回，不再兜底。
    """
    if not base_sql or not prediction:
        return None

    normalized = normalize_prediction_for_patch(remove_think_blocks(prediction))

    for candidate in extract_candidate_blocks(normalized):
        body = (candidate.get("body") or "").strip()
        if not body:
            continue

        if "diff" in (candidate.get("lang") or "") or looks_like_diff(body):
            diff_text = cleanup_diff_text(body)
            if not diff_text:
                return None
            try:
                patched = apply_simple_patch(base_sql, diff_text)
            except Exception:
                patched = None
            return patched

    return None


def sanitize_sql_text(text):
    """
    清理模型输出，尽量提取"可执行查询语句"：
    - 去掉 markdown/解释性噪声
    - 优先返回第一条 SELECT/WITH 语句
    """
    if not text:
        return None

    raw = text.replace("\r\n", "\n").strip()
    if not raw:
        return None

    cleaned_lines = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            cleaned_lines.append(line)
            continue
        if s.startswith("```"):
            continue
        if s.startswith("###"):
            continue
        if s.lower().startswith("diagnosis"):
            continue
        if s.lower().startswith("analysis"):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    if not cleaned:
        return None

    stmts = sqlparse.split(cleaned)
    for st in stmts:
        s = st.strip().rstrip(";")
        if not s:
            continue
        low = s.lower()
        if low.startswith("with ") or low.startswith("select "):
            return s + ";"

    m = re.search(r"\b(with|select)\b", cleaned, re.IGNORECASE)
    if not m:
        return None
    tail = cleaned[m.start():].strip()
    stmts2 = sqlparse.split(tail)
    if not stmts2:
        return tail if tail.endswith(";") else (tail + ";")
    s = stmts2[0].strip().rstrip(";")
    return (s + ";") if s else None


def normalize_sql_for_compare(sql):
    if not sql:
        return ""
    normalized = sqlparse.format(
        sql,
        keyword_case="lower",
        strip_comments=True,
        reindent=False,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    return normalized.rstrip(";")


def sqls_effectively_equal(sql_a, sql_b):
    if not sql_a or not sql_b:
        return False
    return normalize_sql_for_compare(sql_a) == normalize_sql_for_compare(sql_b)


def remove_think_blocks(text):
    if not text:
        return ""
    out = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    return out.strip()


def remove_tagged_reasoning_sections(text):
    """
    Remove common full reasoning sections when they are explicitly tagged.
    This is deliberately separate from remove_think_blocks(), which preserves
    content for backward compatibility in existing patch extraction.
    """
    if not text:
        return ""
    out = text
    for tag in ("think", "reasoning"):
        out = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            "\n",
            out,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return out.strip()


def normalize_prediction_for_patch(text):
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"```\s*diff\s*```\s*diff", "```diff\n", t, flags=re.IGNORECASE)

    outer = re.fullmatch(r"\s*```[ \t]*\n(.*)\n```[ \t]*\s*", t, flags=re.DOTALL)
    if outer:
        inner = (outer.group(1) or "").strip()
        inner_low = inner.lower()
        if "```diff" in inner_low or "diff --git" in inner_low or re.search(r"^--- .*?\n\+\+\+ .*", inner, flags=re.MULTILINE):
            t = inner

    return t


def extract_candidate_blocks(text):
    """
    解析 fenced code block，筛选 sql/diff 候选块。
    """
    candidates = []

    for m in re.finditer(r"```([^\n`]*)\n(.*?)```", text, re.DOTALL):
        lang = (m.group(1) or "").strip().lower()
        body = (m.group(2) or "").strip()
        if not body:
            continue
        if ("sql" in lang) or ("diff" in lang) or looks_like_diff(body):
            candidates.append({"lang": lang, "body": body})

    if not candidates:
        for m in re.finditer(r"```([a-zA-Z0-9_]*)\s+(.*?)```", text, re.DOTALL):
            lang = (m.group(1) or "").strip().lower()
            body = (m.group(2) or "").strip()
            if not body:
                continue
            if ("sql" in lang) or ("diff" in lang) or looks_like_diff(body):
                candidates.append({"lang": lang, "body": body})

    if candidates:
        return candidates

    raw = text.replace("\r\n", "\n")
    m = re.search(r"(?ms)^diff --git .*", raw)
    if m:
        candidates.append({"lang": "diff", "body": raw[m.start():].strip()})
        return candidates

    m = re.search(r"(?ms)^--- .*\n\+\+\+ .*\n@@ .*", raw)
    if m:
        candidates.append({"lang": "diff", "body": raw[m.start():].strip()})
        return candidates

    if looks_like_diff(raw):
        candidates.append({"lang": "diff", "body": raw.strip()})

    return candidates


def looks_like_diff(text):
    lines = text.replace("\r\n", "\n").splitlines()
    if not lines:
        return False

    stripped = text.lstrip()
    if stripped.startswith("diff --git"):
        return True
    if any(l.startswith(("---", "+++", "@@")) for l in lines):
        return True

    plus_minus = 0
    for l in lines:
        if l.startswith("+") or l.startswith("-"):
            plus_minus += 1
    return plus_minus >= 2


def cleanup_diff_text(text):
    """
    尽量把模型输出整理成 apply_simple_patch 可处理的 unified diff：
    - 去掉残留 fence
    - 兼容把 --- / +++ / @@ 压成单行的情况
    - 只截取从首个 diff 头开始的内容
    """
    if not text:
        return None

    t = text.replace("\r\n", "\n").strip()
    if not t:
        return None

    cleaned_lines = []
    for line in t.splitlines():
        if line.strip().startswith("```"):
            continue
        cleaned_lines.append(line)
    t = "\n".join(cleaned_lines).strip()
    if not t:
        return None

    t = re.sub(r"(?m)^diff\s+---\s+", "--- ", t)
    t = re.sub(r"(?m)(--- [^\n]+?)\s+\+\+\+\s+", r"\1\n++++ ", t)
    t = re.sub(r"(?m)(--- [^\n]+?)\s+\+\+\s+", r"\1\n+++ ", t)
    t = re.sub(r"(?m)(\+\+\+ [^\n]+?)\s+(@@)", r"\1\n\2", t)

    starts = []
    for pattern in (r"(?m)^diff --git\b", r"(?m)^---\s+", r"(?m)^@@\s+"):
        m = re.search(pattern, t)
        if m:
            starts.append(m.start())
    if starts:
        t = t[min(starts):].strip()

    return t or None


def apply_simple_patch(original_text, diff_text):
    """
    轻量 unified diff 应用器：
    - 支持 + / - / 空格 上下文行
    - 忽略 --- / +++ / @@ 头信息
    """
    if not original_text or not diff_text:
        return None

    original_lines = original_text.replace("\r\n", "\n").splitlines()
    diff_lines = diff_text.replace("\r\n", "\n").splitlines()

    result_lines = []
    src_idx = 0
    in_hunk = False

    for line in diff_lines:
        if line.startswith("diff --git") or line.startswith("index "):
            continue
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if line.startswith(" "):
            if src_idx < len(original_lines):
                result_lines.append(original_lines[src_idx])
                src_idx += 1
            continue
        if line.startswith("-"):
            if src_idx < len(original_lines):
                src_idx += 1
            continue
        if line.startswith("+"):
            result_lines.append(line[1:])
            continue
        if in_hunk:
            continue
        result_lines.append(line)

    while src_idx < len(original_lines):
        result_lines.append(original_lines[src_idx])
        src_idx += 1

    sql = "\n".join(result_lines).strip()
    return sql or None


def get_response_text(record):
    """
    根据 EVAL_RESPONSE_FIELD 选择从哪个字段读取模型输出。
    """
    if not isinstance(record, dict):
        return ""
    v = record.get(EVAL_RESPONSE_FIELD)
    return v.strip() if isinstance(v, str) else ""


FINAL_SQL_MARKER_RE = re.compile(
    r"(final\s+(?:answer|sql|query)|optimized\s+(?:sql|query)|"
    r"optimization\s+sql|rewritten\s+(?:sql|query)|"
    r"改写后|优化后|最终\s*(?:sql|查询))",
    re.IGNORECASE,
)

ORIGINAL_SQL_MARKER_RE = re.compile(
    r"(original\s+(?:sql|query)|slow\s+(?:sql|query)|input\s+(?:sql|query)|"
    r"given\s+(?:sql|query)|原始\s*(?:sql|查询)|慢\s*(?:sql|查询))",
    re.IGNORECASE,
)


def collect_sql_candidates_from_text(text):
    """
    Collect possible SQL answers from fenced code blocks and labeled final text.
    Each candidate keeps source offsets so we can prefer later/final sections.
    """
    candidates = []
    if not text:
        return candidates

    raw = text.replace("\r\n", "\n")

    for m in re.finditer(r"```([^\n`]*)\n(.*?)```", raw, re.DOTALL):
        lang = (m.group(1) or "").strip().lower()
        body = (m.group(2) or "").strip()
        if not body or "diff" in lang or looks_like_diff(body):
            continue
        if ("sql" in lang) or re.search(r"\b(with|select)\b", body, re.IGNORECASE):
            sql = sanitize_sql_text(body)
            if sql and is_plausible_query_sql(sql):
                candidates.append(
                    {
                        "sql": sql,
                        "start": m.start(),
                        "end": m.end(),
                        "source": "fenced_sql" if "sql" in lang else "fenced_text",
                    }
                )

    # Some models write a final answer after a label without a fenced block.
    markers = list(FINAL_SQL_MARKER_RE.finditer(raw))
    if markers:
        tail = raw[markers[-1].end():].strip()
        sql = sanitize_sql_text(tail)
        if sql and is_plausible_query_sql(sql):
            candidates.append(
                {
                    "sql": sql,
                    "start": markers[-1].end(),
                    "end": len(raw),
                    "source": "final_tail",
                }
            )

    return candidates


def is_plausible_query_sql(sql):
    """
    Guard against prose fragments that happen to contain words like "with" or
    "select" (for example "with a NOT NULL constraint..." or "SELECT list...").
    """
    if not sql:
        return False
    s = re.sub(r"\s+", " ", sql.strip()).strip().rstrip(";")
    low = s.lower()

    if low.startswith("select "):
        # Most benchmark queries have FROM; allow tiny SELECT constants too.
        return (
            " from " in low
            or re.search(r"^select\s+(\d+|'[^']*'|\"[^\"]*\"|true|false|null)\b", low)
            is not None
        )

    if low.startswith("with "):
        # A real CTE should define at least one name AS (...), then a SELECT.
        return bool(
            re.search(r"\bwith\s+(?:recursive\s+)?[a-zA-Z_\"`][\w\"`$]*\s*(?:\([^)]*\))?\s+as\s*\(", s, re.I)
            and re.search(r"\)\s*select\b|\bselect\b", s, re.I)
        )

    return False


def score_end2end_sql_candidate(candidate, text, base_sql=None):
    """
    Score candidate SQL answers. Higher is better.

    Goals:
    - Prefer final/optimized SQL over SQL quoted inside reasoning.
    - Avoid selecting the original slow SQL when base_sql is available.
    - Prefer later candidates because final answers usually come after analysis.
    """
    sql = candidate.get("sql") or ""
    start = int(candidate.get("start") or 0)
    end = int(candidate.get("end") or start)
    source = candidate.get("source") or ""
    raw = text or ""

    score = 0.0
    if source == "final_tail":
        score += 40
    elif source == "fenced_sql":
        score += 20
    else:
        score += 10

    # Later candidates are usually closer to the final answer.
    if raw:
        score += 20.0 * (start / max(len(raw), 1))

    before = raw[max(0, start - 600):start]
    after = raw[end:min(len(raw), end + 200)]
    local = before + "\n" + after
    if FINAL_SQL_MARKER_RE.search(local):
        score += 35
    if ORIGINAL_SQL_MARKER_RE.search(local):
        score -= 35

    low_sql = sql.lower()
    if re.search(r"\b(create|alter|drop|insert|update|delete)\b", low_sql):
        score -= 15
    if low_sql.startswith(("select", "with")):
        score += 10

    if base_sql and sqls_effectively_equal(sql, base_sql):
        score -= 80

    return score


def restore_sql_from_end2end_text_robust(text, base_sql=None):
    """
    Robust end-to-end SQL extraction.

    The old extractor returned the first SQL block. That is brittle for models
    such as Kimi/MiniMax that quote the original SQL inside reasoning before
    emitting the optimized SQL. This function scores all SQL candidates and
    prefers final/optimized non-base candidates.
    """
    if not text:
        return None

    normalized = text.replace("\r\n", "\n").strip()
    candidates = collect_sql_candidates_from_text(normalized)

    if candidates:
        scored = sorted(
            candidates,
            key=lambda c: score_end2end_sql_candidate(c, normalized, base_sql),
            reverse=True,
        )
        best = scored[0].get("sql")
        if best:
            return best

    # Fallback: remove complete tagged reasoning sections and sanitize what is
    # left. This handles responses with no fenced final SQL.
    no_reasoning = remove_tagged_reasoning_sections(normalized)
    if no_reasoning and no_reasoning != normalized:
        sql = sanitize_sql_text(no_reasoning)
        if sql and not (base_sql and sqls_effectively_equal(sql, base_sql)):
            return sql

    return sanitize_sql_text(normalized)


def restore_sql_from_end2end_text(text, base_sql=None):
    if not text:
        return None

    if base_sql:
        return restore_sql_from_end2end_text_robust(text, base_sql)

    normalized = remove_think_blocks(text)
    for candidate in extract_candidate_blocks(normalized):
        lang = (candidate.get("lang") or "").strip().lower()
        body = (candidate.get("body") or "").strip()
        if not body:
            continue
        if "diff" in lang or looks_like_diff(body):
            continue
        sql = sanitize_sql_text(body)
        if sql:
            return sql

    return sanitize_sql_text(normalized)


def restore_sql_for_eval(base_sql, response_text):
    if EVAL_SQL_MODE == "end2end":
        return restore_sql_from_end2end_text(response_text, base_sql)
    return restore_sql_from_prediction(base_sql, response_text)


def infer_db_key_from_unknown(raw_db_key, sql_text):
    """
    对 db=unknown 的样本做兜底路由：
    - 若 SQL 命中 TPC-H 核心表，按当前 benchmark scale 路由到对应 TPC-H 数据集
    - 否则回落到 postgres（保守默认）
    """
    key = normalize_db_key(raw_db_key)
    if key not in ("", "unknown", "null", "none", "n/a", "na"):
        return key

    sql = (sql_text or "").lower()
    for t in TPCH_CORE_TABLES:
        if re.search(rf"\b{re.escape(t)}\b", sql):
            return default_tpch_dataset()
    return "postgres"


def route_config(db_key, sql_text=None):
    db_key = infer_db_key_from_unknown(db_key, sql_text)
    db_key = normalize_db_key(db_key)
    db_mapping = load_json(DB_MAPPING_FILE)
    tpch_mapping = load_json(TPCH_MAPPING_FILE).get("datasets", {})

    small = db_mapping.get("small_db", {})
    preferred_tpch_dataset = default_tpch_dataset()

    if db_key in ("tpch", "tpch_01g", "tpch_1g"):
        dataset, default_db = preferred_tpch_dataset, preferred_tpch_dataset
    elif db_key == "tpch_3g":
        dataset, default_db = "tpch_3g", "tpch_3g"
    else:
        dataset, default_db = None, db_key

    if default_db in ("", "unknown", "null", "none", "n/a", "na"):
        default_db = "postgres"

    if EVAL_DIALECT not in ("postgres", "postgresql"):
        raise ValueError(f"Unsupported EVAL_DIALECT={EVAL_DIALECT}; this release supports PostgreSQL only")

    if dataset:
        cfg = tpch_mapping.get(dataset, {}).get("dialects", {}).get("postgresql", {})
        host = cfg.get("container", "tpch_postgresql_01g") if in_docker() else cfg.get("host", "127.0.0.1")
        port = 5432 if in_docker() else int(cfg.get("port", 5437))
        return {
            "engine": "postgres",
            "host": host,
            "port": port,
            "user": cfg.get("user", "postgres"),
            "password": cfg.get("password", "123456"),
            "database": cfg.get("database", default_db),
        }

    cfg = small.get("postgresql", {})
    if default_db not in ("postgres", "solar_panel", "polar_equipment", "robot_fault_prediction"):
        default_db = "postgres"
    host = cfg.get("container", "postgresql_small") if in_docker() else cfg.get("host", "127.0.0.1")
    port = 5432 if in_docker() else int(cfg.get("port", 7001))
    return {
        "engine": "postgres",
        "host": host,
        "port": port,
        "user": cfg.get("user", "root"),
        "password": cfg.get("password", "123456"),
        "database": default_db,
    }


def get_conn_cursor(db_key, sql_text=None):
    try:
        cfg = route_config(db_key, sql_text=sql_text)
    except Exception as e:
        return None, None, str(e)

    try:
        if cfg["engine"] == "postgres":
            conn = psycopg2.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                dbname=cfg["database"],
            )
            conn.autocommit = False
            with conn.cursor() as _cur:
                _cur.execute(f"SET statement_timeout = {TIMEOUT_SECONDS * 1000}")
            conn.commit()

        else:
            return None, None, f"Unsupported engine: {cfg['engine']}"

    except Exception as e:
        return None, None, f"Connection Failed: {e}"

    try:
        return conn, conn.cursor(), None
    except Exception as e:
        return None, None, f"Cursor Error: {e}"


def rollback_quiet(conn):
    try:
        conn.rollback()
    except Exception:
        pass


def close_cursor_quiet(cursor):
    try:
        if cursor is not None:
            cursor.close()
    except Exception:
        pass


def close_conn_quiet(conn):
    try:
        if conn is not None:
            conn.close()
    except Exception:
        pass


def is_timeout_like_error(err_msg):
    if not err_msg:
        return False
    m = str(err_msg).lower()
    return ("timeout" in m) or ("timed out" in m) or ("query execution was interrupted" in m)


def is_connection_like_error(err_msg):
    if not err_msg:
        return False
    m = str(err_msg).lower()
    return any(x in m for x in [
        "connection failed",
        "cursor error",
        "server has gone away",
        "lost connection",
        "connection reset",
        "broken pipe",
        "could not connect",
        "connection refused",
        "connection unexpectedly closed",
        "terminating connection",
        "ssl syscall error",
    ])


def route_label(cfg):
    if not cfg:
        return ""
    engine = cfg.get("engine", "unknown")
    return f"{engine}:{cfg.get('database', '')}"


def classify_result(error_msg, error_phase, failed_side, is_fail, is_match, pred_row_count, gt_row_count):
    if error_msg:
        if error_msg == "Patch Apply Failed":
            return "patch_apply_failed", False
        if error_msg == "SQL Extract Failed":
            return "sql_extract_failed", False
        if error_msg == "No Base SQL found":
            return "missing_base_sql", False
        if is_connection_like_error(error_msg):
            return "connection_error", True
        if is_timeout_like_error(error_msg):
            if failed_side == "gt":
                return "gt_timeout", True
            return "timeout", True
        if failed_side == "gt":
            return "gt_execution_failed", False
        if error_phase == "warmup":
            return "warmup_failed", True
        if error_phase == "timing":
            return "timing_failed", True
        if error_phase == "compare":
            return "compare_failed", False
        return "execution_error", False

    if is_fail:
        return "internal_eval_error", True

    if not is_match:
        if gt_row_count is not None and pred_row_count is not None and pred_row_count != gt_row_count:
            if pred_row_count > gt_row_count:
                return "pred_result_exceeds_gt", False
            return "pred_mismatch_rowcount", False
        return "pred_mismatch_content", False

    return "ok", False


def _exec_and_fetch(cursor, sql):
    cursor.execute(sql)
    try:
        rows = cursor.fetchmany(2000001)
    except Exception:
        rows = []
    return rows


def _row_fingerprint(row):
    return hashlib.sha256(str(row).encode("utf-8")).digest()


def _fetch_result_signature(cursor, row_limit=None):
    """
    获取结果集指纹（hash），安全版：
    - 超过 MAX_COMPARE_ROWS 也不报错
    - 超过 row_limit 则返回特殊标记
    """
    row_counts = defaultdict(int)
    total_rows = 0

    while True:
        rows = cursor.fetchmany(COMPARE_FETCH_BATCH_SIZE)
        if not rows:
            break

        total_rows += len(rows)

        if row_limit is not None and total_rows > row_limit:
            return "__ROW_LIMIT_EXCEEDED__", total_rows, None

        for row in rows:
            row_counts[_row_fingerprint(row)] += 1

    return dict(row_counts), total_rows, None


def _sql_without_trailing_semicolon(sql):
    return (sql or "").strip().rstrip(";")


def normalize_sql_for_compare(sql):
    if not sql:
        return ""
    normalized = sqlparse.format(
        sql,
        keyword_case="lower",
        strip_comments=True,
        reindent=False,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\s*,\s*", ",", normalized)
    return normalized.rstrip(";")


def sqls_effectively_equal(sql_a, sql_b):
    if not sql_a or not sql_b:
        return False
    return normalize_sql_for_compare(sql_a) == normalize_sql_for_compare(sql_b)


def execute_sql_for_compare(cursor, sql, conn, cfg=None, row_limit=None):
    if not sql:
        return None, 0, "Empty SQL"

    try:
        cursor.execute(sql)
        result_signature, row_count, fetch_err = _fetch_result_signature(cursor, row_limit=row_limit)

        rollback_quiet(conn)

        if fetch_err:
            return None, row_count, fetch_err

        return result_signature, row_count, None

    except Exception as e:
        err_str = str(e)
        rollback_quiet(conn)

        if "canceling statement due to statement timeout" in err_str.lower():
            return None, 0, "Timeout"

        return None, 0, f"Exec Error: {err_str.splitlines()[0]}"


def execute_sql_timed(cursor, sql, conn, cfg=None):
    if not sql:
        return None, "Empty SQL"

    start = time.time()

    try:
        engine = cfg["engine"] if cfg else None
        sql_body = _sql_without_trailing_semicolon(sql)

        if engine == "postgres":
            cursor.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql_body}")
            row = cursor.fetchone()
            plan_root = row[0][0] if row and row[0] else {}
            exec_ms = plan_root.get("Execution Time")
            if exec_ms is None:
                raise ValueError("Execution Time missing in PostgreSQL EXPLAIN ANALYZE output")
            rollback_quiet(conn)
            return float(exec_ms), None

        cursor.execute(sql)
        cursor.fetchall()
        duration_ms = (time.time() - start) * 1000
        rollback_quiet(conn)
        return duration_ms, None

    except Exception as e:
        err_str = str(e)
        rollback_quiet(conn)

        if "canceling statement due to statement timeout" in err_str.lower():
            return None, "Timeout"

        return None, f"Exec Error: {err_str.splitlines()[0]}"


def execute_pair_interleaved(cursor, pred_sql, gt_sql, conn, cfg, num_runs=NUM_RUNS):
    rollback_quiet(conn)
    pred_signature, pred_row_count, pred_err = execute_sql_for_compare(
        cursor,
        pred_sql,
        conn,
        cfg,
    )
    if pred_err:
        return {
            "pred_time_ms": None,
            "gt_time_ms": None,
            "is_match": False,
            "pred_err": pred_err,
            "gt_err": None,
            "error_phase": "compare",
            "failed_side": "pred",
            "pred_row_count": pred_row_count,
            "gt_row_count": None,
            "warmup_done": False,
            "timing_runs_used": 0,
        }

    rollback_quiet(conn)
    gt_signature, gt_row_count, gt_err = execute_sql_for_compare(
        cursor,
        gt_sql,
        conn,
        cfg,
        row_limit=pred_row_count,
    )
    if gt_err:
        return {
            "pred_time_ms": None,
            "gt_time_ms": None,
            "is_match": False,
            "pred_err": None,
            "gt_err": gt_err,
            "error_phase": "compare",
            "failed_side": "gt",
            "pred_row_count": pred_row_count,
            "gt_row_count": gt_row_count,
            "warmup_done": False,
            "timing_runs_used": 0,
        }

    is_match = pred_row_count == gt_row_count and pred_signature == gt_signature
    if not is_match:
        return {
            "pred_time_ms": None,
            "gt_time_ms": None,
            "is_match": False,
            "pred_err": None,
            "gt_err": None,
            "error_phase": "",
            "failed_side": "",
            "pred_row_count": pred_row_count,
            "gt_row_count": gt_row_count,
            "warmup_done": False,
            "timing_runs_used": 0,
        }

    pred_durations = []
    gt_durations = []

    adaptive_num_runs = max(1, num_runs)

    for run_idx in range(adaptive_num_runs):
        pairs = [("pred", pred_sql), ("gt", gt_sql)]
        random.shuffle(pairs)
        run_results = {}

        for label, sql in pairs:
            rollback_quiet(conn)
            duration, err = execute_sql_timed(cursor, sql, conn, cfg)
            if err:
                if label == "pred":
                    return {
                        "pred_time_ms": None,
                        "gt_time_ms": None,
                        "is_match": is_match,
                        "pred_err": err,
                        "gt_err": None,
                        "error_phase": "timing",
                        "failed_side": "pred",
                        "pred_row_count": pred_row_count,
                        "gt_row_count": gt_row_count,
                        "warmup_done": False,
                        "timing_runs_used": run_idx,
                    }
                return {
                    "pred_time_ms": None,
                    "gt_time_ms": None,
                    "is_match": is_match,
                    "pred_err": None,
                    "gt_err": err,
                    "error_phase": "timing",
                    "failed_side": "gt",
                    "pred_row_count": pred_row_count,
                    "gt_row_count": gt_row_count,
                    "warmup_done": False,
                    "timing_runs_used": run_idx,
                }
            run_results[label] = duration

        pred_durations.append(run_results["pred"])
        gt_durations.append(run_results["gt"])

        if (
            adaptive_num_runs > 2
            and run_idx >= 1
            and max(run_results["pred"], run_results["gt"]) >= LONG_RUNNING_THRESHOLD_MS
        ):
            break

    return {
        "pred_time_ms": statistics.median(pred_durations),
        "gt_time_ms": statistics.median(gt_durations),
        "is_match": is_match,
        "pred_err": None,
        "gt_err": None,
        "error_phase": "",
        "failed_side": "",
        "pred_row_count": pred_row_count,
        "gt_row_count": gt_row_count,
        "warmup_done": False,
        "timing_runs_used": len(pred_durations),
    }


def record_resume_key(record):
    instance_id = str(record.get("instance_id", ""))
    slow_sql_type = str(record.get("slow_sql_type", ""))
    base_sql = record.get("base_sql")
    base_sql_text = base_sql.strip() if isinstance(base_sql, str) else ""
    base_sql_hash = hashlib.sha256(base_sql_text.encode("utf-8")).hexdigest() if base_sql_text else ""
    return (instance_id, slow_sql_type, base_sql_hash)


def load_done_keys(output_file):
    done = set()
    if not os.path.exists(output_file):
        return done
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                key = record_resume_key(record)
                done.add(key)
            except json.JSONDecodeError:
                continue
    return done


def record_matches_dialect(record):
    target = normalize_dialect(EVAL_DIALECT)
    sample = record_dialect(record)
    return sample == target


def worker_bucket_for_record(record):
    try:
        cfg = route_config(record.get("db"), sql_text=record.get("base_sql"))
    except Exception:
        return "small"

    host = str(cfg.get("host", "")).lower()
    database = normalize_db_key(cfg.get("database"))
    if host.startswith("tpch_") or database in ("tpch", "tpch_01g", "tpch_1g", "tpch_3g"):
        return "tpch"
    return "small"


def finalize_result_record(result_record):
    reward = int(result_record.get("reward", 0) or 0)
    return reward, bool(result_record.get("is_match", False))


def evaluate_record(original_data):
    result_record = original_data.copy()
    response_text = get_response_text(original_data)
    db_key = original_data.get("db")
    gt_sql = original_data.get("base_sql")

    pred_time_raw = None
    gt_time_raw = None
    speedup = 0.0
    error_msg = None
    error_type = ""
    error_phase = ""
    retry_recommended = False
    is_fail = False
    is_pass = False
    is_match = False
    pred_row_count = None
    gt_row_count = None
    timing_runs_used = 0
    warmup_done = False
    pred_err = None
    gt_err = None
    failed_side = ""

    conn = None
    cursor = None
    cfg = None

    conn, cursor, conn_err = get_conn_cursor(db_key, sql_text=gt_sql)
    if not conn_err:
        cfg = route_config(db_key, sql_text=gt_sql)

    try:
        if conn_err:
            is_fail = True
            error_msg = conn_err
            error_phase = "prepare"

        elif not gt_sql:
            is_fail = True
            error_msg = "No Base SQL found"
            error_phase = "prepare"

        else:
            pred_sql = restore_sql_for_eval(gt_sql, response_text)
            if not pred_sql:
                is_fail = True
                error_msg = "SQL Extract Failed" if EVAL_SQL_MODE == "end2end" else "Patch Apply Failed"
                error_phase = "prepare"
            else:
                try:
                    outcome = execute_pair_interleaved(
                        cursor, pred_sql, gt_sql, conn, cfg
                    )
                    pred_time_raw = outcome["pred_time_ms"]
                    gt_time_raw = outcome["gt_time_ms"]
                    is_match = outcome["is_match"]
                    pred_row_count = outcome["pred_row_count"]
                    gt_row_count = outcome["gt_row_count"]
                    timing_runs_used = outcome["timing_runs_used"]
                    warmup_done = outcome["warmup_done"]
                    error_phase = outcome["error_phase"]
                    pred_err = outcome["pred_err"]
                    gt_err = outcome["gt_err"]

                    if not is_fail:
                        if pred_err:
                            is_fail = True
                            error_msg = pred_err
                        elif gt_err:
                            is_fail = True
                            error_msg = gt_err
                        else:
                            is_pass = True
                            p_time = pred_time_raw if pred_time_raw and pred_time_raw > 0 else 0.001
                            g_time = gt_time_raw if gt_time_raw is not None else 0
                            speedup = min(g_time / p_time, 1000.0)

                except Exception as e:
                    is_fail = True
                    error_msg = str(e)
                    error_phase = error_phase or "internal"

    finally:
        close_cursor_quiet(cursor)
        close_conn_quiet(conn)

    if not error_msg:
        failed_side = ""
    elif gt_err and error_msg == gt_err:
        failed_side = "gt"
    else:
        failed_side = "pred"

    error_type, retry_recommended = classify_result(
        error_msg,
        error_phase,
        failed_side,
        is_fail,
        is_match,
        pred_row_count,
        gt_row_count,
    )

    reward = 0
    if is_fail:
        reward = 0
    elif is_pass and not is_match:
        reward = -1
    elif is_pass and is_match:
        reward = 1 if speedup > 1.2 else 0

    result_record["gt_time_ms"] = round(gt_time_raw, 2) if gt_time_raw is not None else 0
    result_record["exec_time_ms"] = round(pred_time_raw, 2) if pred_time_raw is not None else 0
    result_record["speedup"] = round(speedup, 4)
    result_record["is_fail"] = is_fail
    result_record["is_pass"] = is_pass
    result_record["is_match"] = is_match
    result_record["error_msg"] = error_msg if error_msg else ""
    result_record["error_type"] = error_type
    result_record["error_phase"] = error_phase
    result_record["retry_recommended"] = retry_recommended
    result_record["pred_row_count"] = pred_row_count if pred_row_count is not None else 0
    result_record["gt_row_count"] = gt_row_count if gt_row_count is not None else 0
    result_record["timing_runs_used"] = timing_runs_used
    result_record["warmup_done"] = warmup_done
    result_record["db_route"] = route_label(cfg)
    result_record["reward"] = reward
    result_record["eval_dialect"] = EVAL_DIALECT
    result_record["eval_sql_mode"] = EVAL_SQL_MODE
    result_record["eval_response_field"] = EVAL_RESPONSE_FIELD
    result_record["sample_dialect"] = record_dialect(original_data)
    return result_record


def sequential_process_records(records, f_out):
    processed_count = 0
    match_count = 0
    reward_sum = 0

    for original_data in records:
        result_record = evaluate_record(original_data)
        reward, is_match = finalize_result_record(result_record)
        f_out.write(json.dumps(result_record, ensure_ascii=False) + "\n")
        f_out.flush()
        processed_count += 1
        reward_sum += reward
        if is_match:
            match_count += 1

    return processed_count, match_count, reward_sum


def split_worker_loop(worker_name, task_queue, result_queue):
    while True:
        task = task_queue.get()
        if task is None:
            task_queue.task_done()
            return

        idx, original_data = task
        try:
            result_record = evaluate_record(original_data)
        except Exception as e:
            result_record = original_data.copy()
            result_record["gt_time_ms"] = 0
            result_record["exec_time_ms"] = 0
            result_record["speedup"] = 0.0
            result_record["is_fail"] = True
            result_record["is_pass"] = False
            result_record["is_match"] = False
            result_record["error_msg"] = str(e)
            result_record["error_type"] = "internal_eval_error"
            result_record["error_phase"] = "internal"
            result_record["retry_recommended"] = True
            result_record["pred_row_count"] = 0
            result_record["gt_row_count"] = 0
            result_record["timing_runs_used"] = 0
            result_record["warmup_done"] = False
            result_record["db_route"] = worker_name
            result_record["reward"] = 0
            result_record["eval_dialect"] = EVAL_DIALECT
            result_record["sample_dialect"] = record_dialect(original_data)
        result_queue.put((idx, result_record))
        task_queue.task_done()


def split_process_records(records, f_out):
    queues_by_bucket = {
        "tpch": queue.Queue(),
        "small": queue.Queue(),
    }
    result_queue = queue.Queue()
    workers = []
    worker_layout = {
        "tpch": TPCH_WORKER_COUNT,
        "small": SMALL_DB_WORKER_COUNT,
    }

    for bucket_name, worker_count in worker_layout.items():
        for worker_idx in range(worker_count):
            worker_name = f"{bucket_name}-{worker_idx}"
            worker = threading.Thread(
                target=split_worker_loop,
                args=(worker_name, queues_by_bucket[bucket_name], result_queue),
                daemon=True,
                name=f"eval-{worker_name}",
            )
            worker.start()
            workers.append(worker)

    for idx, original_data in enumerate(records):
        bucket = worker_bucket_for_record(original_data)
        queues_by_bucket[bucket].put((idx, original_data))

    for bucket_name, worker_count in worker_layout.items():
        for _ in range(worker_count):
            queues_by_bucket[bucket_name].put(None)

    processed_count = 0
    match_count = 0
    reward_sum = 0
    completed_count = 0

    while completed_count < len(records):
        _, result_record = result_queue.get()
        reward, is_match = finalize_result_record(result_record)
        f_out.write(json.dumps(result_record, ensure_ascii=False) + "\n")
        f_out.flush()
        processed_count += 1
        reward_sum += reward
        if is_match:
            match_count += 1
        completed_count += 1

    for bucket_name in ("tpch", "small"):
        queues_by_bucket[bucket_name].join()
    for worker in workers:
        worker.join()

    return processed_count, match_count, reward_sum


def process_one_file(input_file, output_file, filter_map=None):
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    instance_id_counts = defaultdict(int)
    if filter_map:
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                instance_id_counts[str(data.get("instance_id", ""))] += 1
            except Exception:
                continue

    done_keys = load_done_keys(output_file)
    pending_records = []
    seen_pending_keys = set()

    for line in lines:
        if not line.strip():
            continue
        try:
            original_data = json.loads(line)
        except Exception:
            continue

        # if not record_matches_dialect(original_data):
        #     continue

        if filter_map and not should_keep_record(original_data, filter_map, instance_id_counts):
            continue

        cur_key = record_resume_key(original_data)
        if cur_key in done_keys:
            continue
        if cur_key in seen_pending_keys:
            continue

        pending_records.append(original_data)
        seen_pending_keys.add(cur_key)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "a", encoding="utf-8") as f_out:
        if pending_records:
            return split_process_records(pending_records, f_out)


def main():
    print("=" * 60)
    print(f"🚀 SQL Eval Runner ({EVAL_DIALECT})")
    print(f"Input: {INPUT_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Filter: {FILTER_FILE}")
    print(f"SQL Mode: {EVAL_SQL_MODE}")
    print(f"Response Field: {EVAL_RESPONSE_FIELD}")
    print(
        f"Workers: {SPLIT_WORKER_COUNT} "
        f"(tpch={TPCH_WORKER_COUNT}, postgresql_small={SMALL_DB_WORKER_COUNT}, no pooled connections)"
    )
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filter_map = None
    if FILTER_FILE and os.path.exists(FILTER_FILE):
        filter_map = load_filter_keys(FILTER_FILE)

    if INPUT_FILE:
        selected = INPUT_FILE if os.path.isabs(INPUT_FILE) else os.path.join(INPUT_DIR, INPUT_FILE)
        if not os.path.exists(selected):
            print(f"[ERROR] EVAL_INPUT_FILE not found: {selected}")
            return
        jsonl_files = [selected]
    else:
        jsonl_files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.jsonl")))
        if not jsonl_files:
            print(f"[ERROR] No .jsonl files found in {INPUT_DIR}")
            return

    total_processed = 0
    total_match = 0
    total_reward = 0

    for input_path in jsonl_files:
        filename = os.path.basename(input_path)
        output_path = os.path.join(OUTPUT_DIR, filename)
        p, m, r = process_one_file(input_path, output_path, filter_map=filter_map)
        total_processed += p
        total_match += m
        total_reward += r

    print("=" * 60)
    print(f"Processed: {total_processed}")
    if total_processed:
        print(f"Match: {total_match}/{total_processed} ({(total_match / total_processed) * 100:.1f}%)")
    print(f"Reward: {total_reward}")
    print("=" * 60)


if __name__ == "__main__":
    main()
