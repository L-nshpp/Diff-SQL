import json
import time
import re
import psycopg2
import psycopg2.errors
from typing import Any
import hashlib
import traceback
import os
from datetime import datetime

# ==============================================================================
# 0. 📝 全局日志配置
# ==============================================================================
EXECUTION_LOG_FILE = os.environ.get(
    "SQL_REWARD_LOG_FILE",
    "logs/sql_execution_pg_details.jsonl",
)

def log_execution_detail(info_dict):
    try:
        os.makedirs(os.path.dirname(EXECUTION_LOG_FILE), exist_ok=True)
        info_dict["log_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(EXECUTION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(info_dict, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Write Log Error: {e}")

# ==============================================================================
# 1. 🌍 全局数据库配置（PostgreSQL）
# ==============================================================================
PG_CONFIG = {
    "user": os.environ.get("PGUSER", os.environ.get("POSTGRES_USER", "postgres")),
    "password": os.environ.get("PGPASSWORD", os.environ.get("POSTGRES_PASSWORD", "123456")),
    "host": os.environ.get("PGHOST", os.environ.get("POSTGRES_HOST", "localhost")),
    "port": os.environ.get("PGPORT", os.environ.get("POSTGRES_PORT", "5432")),
}

def normalize_db_key(db_key: str) -> str:
    """
    统一 db key 逻辑：
    - tpch / TPCH / tpch_01g / unknown 都归到 tpch
    - 其他按原名走
    """
    if not db_key:
        return "tpch"

    db_key_lower = str(db_key).strip().lower()

    if db_key_lower in {"tpch", "tpch_01g", "unknown"}:
        return "tpch"

    return db_key_lower

DB_CONFIGS = {
    "solar_panel":            (PG_CONFIG, os.environ.get("PG_DB_SOLAR", "solar_panel")),
    "polar_equipment":        (PG_CONFIG, os.environ.get("PG_DB_POLAR", "polar_equipment")),
    "robot_fault_prediction": (PG_CONFIG, os.environ.get("PG_DB_ROBOT", "robot_fault_prediction")),
    "tpch":                   (PG_CONFIG, os.environ.get("PG_DB_TPCH", "tpch_01g")),
}

# ==============================================================================
# 2. 🛠️ 核心工具函数
# ==============================================================================
def get_db_cursor(db_key):
    normalized_key = normalize_db_key(db_key)
    target_key = normalized_key if normalized_key in DB_CONFIGS else "tpch"
    instance_config, real_db_name = DB_CONFIGS[target_key]

    try:
        connect_args = instance_config.copy()
        connect_args["dbname"] = real_db_name
        connect_args["connect_timeout"] = int(os.environ.get("PG_CONNECT_TIMEOUT", "10"))
        conn = psycopg2.connect(**connect_args)
        conn.autocommit = False
    except Exception as e:
        return None, None, f"Connection Failed ({real_db_name}@{instance_config['host']}:{instance_config['port']}): {str(e)}"

    try:
        return conn, conn.cursor(), None
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return None, None, f"Cursor Error: {str(e)}"

def apply_simple_patch(original_text, diff_text):
    if not original_text or not diff_text:
        return None
    try:
        original_lines = original_text.replace("\r\n", "\n").splitlines()
        diff_lines = diff_text.replace("\r\n", "\n").splitlines()
        result_lines = []
        src_idx = 0
        i = 0

        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                i += 1
                continue
            if line.startswith(" "):
                if src_idx < len(original_lines):
                    result_lines.append(original_lines[src_idx])
                    src_idx += 1
            elif line.startswith("-"):
                src_idx += 1
            elif line.startswith("+"):
                result_lines.append(line[1:])
            i += 1

        while src_idx < len(original_lines):
            result_lines.append(original_lines[src_idx])
            src_idx += 1

        return "\n".join(result_lines).strip()
    except Exception:
        return None

def extract_patch_from_response(response_str):
    if not response_str:
        return None

    pattern = r"### Verified Patch:.*?```(?:diff|sql)?\s*(.*?)```"
    match = re.search(pattern, response_str, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)

    candidates = re.findall(r"```(?:diff|sql)?\s*(.*?)```", response_str, re.DOTALL)
    if candidates:
        return candidates[0]

    return None

def patch_has_effective_edit(patch_text: str) -> bool:
    """
    判断 patch 是否包含真正的编辑内容，而不是空 patch / 只有 header / 只有注释。
    规则：
    - 忽略空行
    - 忽略 --- / +++ / @@ 这些 diff header
    - 只有以 '+' 或 '-' 开头，且不是 header 的行，才算有效编辑
    """
    if patch_text is None:
        return False

    lines = patch_text.replace("\r\n", "\n").splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("---") or stripped.startswith("+++") or stripped.startswith("@@"):
            continue
        if line.startswith("+") or line.startswith("-"):
            return True

    return False

def execute_sql_bounded(cursor, sql, time_limit_ms):
    if not sql:
        return None, 0, None, "Empty SQL"

    timeout_val = int(os.environ.get("PG_REWARD_TIMEOUT_MS", "200000"))
    start = time.time()

    try:
        cursor.execute(f"SET statement_timeout = {timeout_val};")
        cursor.execute(sql)

        rows = []
        if cursor.description:
            rows = cursor.fetchall()

        duration = (time.time() - start) * 1000

        try:
            sorted_rows = str(sorted(rows, key=lambda x: str(x)))
        except Exception:
            sorted_rows = str(rows)

        return duration, len(rows), sorted_rows, None

    except psycopg2.errors.QueryCanceled:
        return None, 0, None, "TIMEOUT_EXCEEDED"

    except Exception as e:
        msg = str(e).lower()
        if "statement timeout" in msg or "canceling statement due to statement timeout" in msg:
            return None, 0, None, "TIMEOUT_EXCEEDED"
        return None, 0, None, str(e)

def normalize_sql(s: str) -> str:
    """
    标准化 SQL：用于检测是否回退 / no-op
    - 去掉单行注释
    - 去掉多余空格
    - 去掉末尾分号
    - 转小写
    """
    if not s:
        return ""

    s = re.sub(r"--.*?$", "", s, flags=re.MULTILINE)
    s = " ".join(s.strip().split())
    s = re.sub(r";+\s*$", "", s)

    return s.lower().strip()

# ==============================================================================
# 3. 🎯 Reward Function (Audit & Fix 专用版)
# ==============================================================================
def sql_optimize(data_source, solution_str, ground_truth, extra_info=None):
    log_info = {
        "status": "init",
        "reward": 0.0,
        "error_msg": None,
        "generated_sql": None,
        "db_name": ground_truth.get("db", "unknown") if ground_truth else "unknown",
        "base_sql": ground_truth.get("base_sql", "") if ground_truth else "",
    }

    # 1. 解析 Ground Truth
    if not ground_truth:
        log_info["status"] = "missing_gt"
        log_execution_detail(log_info)
        return 0.0

    base_sql = ground_truth.get("base_sql", "")
    db_key = ground_truth.get("db", "unknown")
    gt_res_hash = ground_truth.get("base_result_hash")
    gt_time = ground_truth.get("base_exec_time", 1000)

    if gt_res_hash is None:
        log_info["status"] = "missing_gt_hash"
        log_execution_detail(log_info)
        return 0.0

    # 2. 解析 Patch
    patch_content = extract_patch_from_response(solution_str)

    if patch_content is None:
        log_info["status"] = "patch_extract_failed"
        log_info["reward"] = -1.0
        log_execution_detail(log_info)
        return -1.0

    if not patch_has_effective_edit(patch_content):
        log_info["status"] = "empty_patch"
        log_info["reward"] = -1.0
        log_info["error_msg"] = "Patch format exists but contains no effective edit."
        log_execution_detail(log_info)
        return -1.0

    pred_sql = apply_simple_patch(base_sql, patch_content)
    log_info["generated_sql"] = pred_sql

    if not pred_sql:
        log_info["status"] = "patch_apply_failed"
        log_info["reward"] = -1.0
        log_execution_detail(log_info)
        return -1.0

    # 2.5 提前拦截 no-op / rollback（例如只多了一个 ';'）
    normalized_base_sql = normalize_sql(base_sql)
    normalized_pred_sql = normalize_sql(pred_sql)

    if normalized_pred_sql == normalized_base_sql:
        log_info["status"] = "patch_noop_or_revert"
        log_info["reward"] = -0.1
        log_info["error_msg"] = "Applied patch does not make a substantive change."
        log_execution_detail(log_info)
        return -0.1

    # 3. 连接数据库
    conn, cursor, conn_err = get_db_cursor(db_key)
    if conn_err:
        log_info["status"] = "db_connect_failed"
        log_info["error_msg"] = conn_err
        log_execution_detail(log_info)
        return 0.0

    reward = 0.0
    try:
        conn.rollback()

        pred_time, _, pred_res, pred_err = execute_sql_bounded(cursor, pred_sql, gt_time)

        log_info["execution_time"] = pred_time
        log_info["error_msg"] = pred_err

        if pred_err == "TIMEOUT_EXCEEDED":
            log_info["status"] = "timeout"
            reward = 0.1

        elif pred_err:
            log_info["status"] = "sql_exec_error"
            reward = -1.0

        else:
            curr_hash = hashlib.md5(str(pred_res).encode()).hexdigest()

            if curr_hash == gt_res_hash:
                is_reverted = normalize_sql(pred_sql) == normalize_sql(base_sql)

                if is_reverted:
                    log_info["status"] = "success_revert_bad"
                    reward = -0.1
                else:
                    log_info["status"] = "success_fixed_strategy"
                    reward = 1.0
            else:
                log_info["status"] = "success_mismatch"
                reward = -0.5

    except Exception as e:
        error_content = f"{str(e)}\n{traceback.format_exc()}"
        log_info["status"] = "code_crash"
        log_info["error_msg"] = error_content
        reward = 0.0

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    log_info["reward"] = float(reward)
    log_execution_detail(log_info)

    return float(reward)
