"""收敛验证：① 全新空库(ensure_schema→migrations) 与 ② 存量库(migrations) 结构必须完全一致。

同时验证：
- V1 ensure_schema 的全部 DDL 在迁移后的库上重放无副作用（AST 同时支持 Assign/AnnAssign，
  上一轮的 `ENSURE_SQL` 是带注解赋值，只查 ast.Assign 会静默取到 0 条 → 假通过）；
- V1 代码路径（不写 object_type/object_id）的 INSERT 仍可用，触发器自动补齐；
- 重建 attachments 时按行复制，数据不丢。
"""
from __future__ import annotations

import ast
import importlib.util
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
V1_SCHEMA = Path("/opt/data/crm/app/schema.py")
PROD_DB = Path("/opt/data/crm/crm.db")

spec = importlib.util.spec_from_file_location("mig", HERE / "migrations_v2.py")
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)


def v1_statements() -> list[str]:
    tree = ast.parse(V1_SCHEMA.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "ENSURE_SQL" for t in targets):
            for elt in value.elts:
                out.append(ast.literal_eval(elt))
    assert out, "未能从 schema.py 提取 ENSURE_SQL"
    return out


def run_ensure_schema(conn: sqlite3.Connection) -> int:
    stmts = v1_statements()
    for s in stmts:
        conn.execute(s)
    conn.commit()
    return len(stmts)


def shape(conn: sqlite3.Connection) -> dict:
    """结构指纹：表→列(名,类型,notnull,默认)、索引、触发器、外键。"""
    tables = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    out: dict = {}
    for t in tables:
        cols = tuple((r[1], (r[2] or "").upper(), r[3], r[4], r[5])
                     for r in conn.execute(f'PRAGMA table_info("{t}")'))
        idx = tuple(sorted((r[1], r[2]) for r in conn.execute(f'PRAGMA index_list("{t}")')))
        fks = tuple(sorted((tuple(r[2:5]) for r in conn.execute(f'PRAGMA foreign_key_list("{t}")'))))
        trg = tuple(sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (t,))))
        out[t] = {"cols": cols, "idx": idx, "fks": fks, "trg": trg}
    return out


def build_fresh(path: Path) -> sqlite3.Connection:
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    n = run_ensure_schema(conn)
    print(f"[fresh] V1 ensure_schema: {n} 条 DDL")
    mig.apply(path, backup=False, verbose=False)
    return conn


def build_upgraded(path: Path) -> sqlite3.Connection:
    path.unlink(missing_ok=True)
    src = sqlite3.connect(PROD_DB)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    print(f"[upgraded] 存量副本 rows: customers={mig.row_count(conn,'customers')} "
          f"deals={mig.row_count(conn,'deals')} follow_ups={mig.row_count(conn,'follow_ups')}")
    print(f"[upgraded] V1 ensure_schema 重放: {run_ensure_schema(conn)} 条（必须无副作用）")
    mig.apply(path, backup=False, verbose=False)
    return conn


def diff(a: dict, b: dict) -> list[str]:
    problems: list[str] = []
    if set(a) != set(b):
        problems.append(f"表集合不同: only_fresh={set(a)-set(b)} only_upgraded={set(b)-set(a)}")
    for t in sorted(set(a) & set(b)):
        for key in ("cols", "idx", "fks", "trg"):
            if a[t][key] != b[t][key]:
                problems.append(f"{t}.{key} 不同:\n  fresh={a[t][key]}\n  upgraded={b[t][key]}")
    return problems


def main() -> int:
    fresh = build_fresh(HERE / "conv-fresh.db")
    upgraded = build_upgraded(HERE / "conv-upgraded.db")

    problems = diff(shape(fresh), shape(upgraded))
    assert not problems, "结构未收敛:\n" + "\n".join(problems)
    print(f"✓ 结构完全一致（{len(shape(fresh))} 张表）")

    # --- V1 代码路径兼容：不写 object_type/object_id ---
    conn = upgraded
    conn.execute("INSERT INTO follow_ups (customer_id, deal_id, content, next_date, created_at)"
                 " VALUES (1, NULL, 'V1路径：只挂客户', NULL, '2026-10-30T00:00:00Z')")
    conn.execute("INSERT INTO follow_ups (customer_id, deal_id, content, next_date, created_at)"
                 " VALUES (1, 1, 'V1路径：挂商机', NULL, '2026-10-30T00:00:00Z')")
    fu = conn.execute("SELECT object_type, object_id FROM follow_ups WHERE content LIKE 'V1路径%' "
                      "ORDER BY id").fetchall()
    assert fu == [("customer", 1), ("deal", 1)], fu
    print(f"✓ V1 路径 INSERT follow_ups 触发器补齐: {fu}")

    conn.execute("INSERT INTO attachments (follow_up_id, storage_key, file_name, mime_type, size, created_at)"
                 " VALUES (1, '2026/10/30/a.jpg', 'a.jpg', 'image/jpeg', 10, '2026-10-30T00:00:00Z')")
    att = conn.execute("SELECT object_type, object_id, follow_up_id FROM attachments").fetchall()
    assert att == [("follow_up", 1, 1)], att
    print(f"✓ V1 路径 INSERT attachments 触发器补齐: {att}")

    # --- 订单截图：follow_up_id 允许 NULL（V1 的 NOT NULL 已放宽）---
    conn.execute("INSERT INTO attachments (object_type, object_id, storage_key, file_name, mime_type, size, created_at)"
                 " VALUES ('order_payment', 999, '2026/10/30/p.jpg', 'p.jpg', 'image/jpeg', 20,"
                 " '2026-10-30T00:00:00Z')")
    print("✓ 订单截图行可写（object_type=order_payment, follow_up_id=NULL）")
    conn.rollback()
    conn.close()
    fresh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())