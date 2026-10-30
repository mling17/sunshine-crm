"""文档 DDL 可执行性验证：把 PLANNER-V2.md 里所有 ```sql 代码块原样抽出来，
在 crm.db 副本上顺序执行，然后与 migrations_v2.py 跑出来的结构逐项比对。

目的：证明文档里贴的每条 DDL 都能直接执行，而不是"看起来能执行"。
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import sqlite3
import sys
from pathlib import Path

DOC = Path("/opt/data/crm/docs/PLANNER-V2.md")
PROD = Path("/opt/data/crm/crm.db")
HERE = Path(__file__).parent

spec = importlib.util.spec_from_file_location("mig", HERE / "migrations_v2.py")
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)


def sql_blocks(text: str) -> list[tuple[int, str]]:
    blocks = []
    for m in re.finditer(r"```sql\n(.*?)```", text, re.S):
        start_line = text[:m.start()].count("\n") + 1
        blocks.append((start_line, m.group(1)))
    return blocks


def split_statements(block: str):
    """按 sqlite3.complete_statement 切句：能正确处理 CREATE TRIGGER ... BEGIN ... END 里的分号。"""
    statements, buf = [], []
    for line in block.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        candidate = "\n".join(buf).strip()
        if candidate and sqlite3.complete_statement(candidate):
            statements.append(candidate.rstrip(";").strip())
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return [s for s in statements if s]


def shape(conn):
    tables = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    out = {}
    for t in tables:
        out[t] = (
            tuple((r[1], (r[2] or "").upper(), r[3], r[4], r[5])
                  for r in conn.execute(f'PRAGMA table_info("{t}")')),
            tuple(sorted((r[1], r[2]) for r in conn.execute(f'PRAGMA index_list("{t}")'))),
            tuple(sorted(tuple(r[2:5]) for r in conn.execute(f'PRAGMA foreign_key_list("{t}")'))),
            tuple(sorted(r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (t,)))),
        )
    return out


def main() -> int:
    text = DOC.read_text()
    blocks = sql_blocks(text)
    assert blocks, "文档里没抽到 sql 代码块"

    doc_db = Path("/tmp/ddl-doc.db")
    doc_db.unlink(missing_ok=True)
    shutil.copy(PROD, doc_db)
    conn = sqlite3.connect(doc_db)
    conn.execute("PRAGMA foreign_keys=OFF")   # §1.4 重建要求（文档 §1.4 已写明）

    total = 0
    for start_line, block in blocks:
        stmts = split_statements(block)
        for stmt in stmts:
            head = " ".join(stmt.split())[:60]
            try:
                conn.execute(stmt)
            except sqlite3.Error as exc:
                print(f"✗ 文档第 {start_line} 行的 DDL 执行失败: {exc}\n  语句: {head}")
                return 1
            total += 1
        conn.commit()
    conn.close()
    print(f"✓ 文档 {len(blocks)} 个 sql 代码块 / {total} 条语句在 crm.db 副本上全部执行成功")

    # 与迁移脚本结果比对
    mig_db = Path("/tmp/ddl-mig.db")
    mig_db.unlink(missing_ok=True)
    shutil.copy(PROD, mig_db)
    mig.apply(mig_db, backup=False, verbose=False)

    a, b = shape(sqlite3.connect(doc_db)), shape(sqlite3.connect(mig_db))
    problems = []
    if set(a) != set(b):
        problems.append(f"表集合不同: 文档缺={set(b)-set(a)} 文档多={set(a)-set(b)}")
    for t in sorted(set(a) & set(b)):
        for i, key in enumerate(("列", "索引", "外键", "触发器")):
            if a[t][i] != b[t][i]:
                problems.append(f"{t}.{key} 不一致:\n  文档={a[t][i]}\n  脚本={b[t][i]}")
    assert not problems, "\n".join(problems)
    print(f"✓ 文档 DDL 建出的结构 == 迁移脚本建出的结构（{len(a)} 张表，列/索引/外键/触发器逐项一致）")

    # 数据仍在（文档 DDL 也走了重建复制）
    conn = sqlite3.connect(doc_db)
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("customers", "deals", "follow_ups", "tags", "attachments")}
    assert counts == {"customers": 2, "deals": 1, "follow_ups": 2, "tags": 1, "attachments": 0}, counts
    print(f"✓ 文档 DDL 执行后存量数据完好: {counts}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())