"""中断收敛验证：在「跑到一半」的库上重跑 M1，必须收敛且数据不丢。

覆盖两个生产风险：
1. 迁移进程被杀（每条语句自动提交，库里留下中间态）→ 重跑要能接着走；
2. attachments 有存量行时（4 张跟进照片）→ 重建必须按行复制，不能丢。
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
PROD_DB = Path("/opt/data/crm/crm.db")

spec = importlib.util.spec_from_file_location("mig", HERE / "migrations_v2.py")
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)

NOW = "2026-10-30T22:50:00+08:00"


def fresh_copy(path: Path, with_photos: int = 0) -> None:
    path.unlink(missing_ok=True)
    src = sqlite3.connect(PROD_DB)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.close()
    if with_photos:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys=ON")
        for i in range(with_photos):
            conn.execute(
                "INSERT INTO attachments (follow_up_id, storage_key, file_name, mime_type, size, created_at)"
                " VALUES (1, ?, ?, 'image/jpeg', 2048, ?)",
                (f"2026/10/30/photo{i}.jpg", f"photo{i}.jpg", NOW))
        conn.commit()
        conn.close()


def run_partial(path: Path, upto: int) -> tuple[int, int]:
    """模拟中断：只跑到前 upto 条语句，逐条提交。"""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=OFF")
    done = skipped = 0
    for label, guard, sql in mig.STATEMENTS[:upto]:
        if guard is not None and guard(conn):
            skipped += 1
            continue
        conn.execute(sql)
        conn.commit()
        done += 1
    conn.close()
    return done, skipped


def state(path: Path, expect_photos: int) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    q = lambda s: conn.execute(s).fetchone()[0]
    assert q("SELECT COUNT(*) FROM customers") == 2, "客户数"
    assert q("SELECT COUNT(*) FROM deals") == 1, "商机数"
    assert q("SELECT stage FROM deals WHERE id=1") == "confirm", "stage 映射"
    assert q("SELECT COUNT(*) FROM follow_ups") == 2, "跟进数"
    assert q("SELECT COUNT(*) FROM follow_ups WHERE object_id IS NULL") == 0, "跟进 object_id 未回填"
    assert q("SELECT object_type FROM follow_ups WHERE id=2") == "deal"
    assert q("SELECT COUNT(*) FROM attachments") == expect_photos, "附件数丢失"
    if expect_photos:
        assert q("SELECT COUNT(*) FROM attachments WHERE object_type='follow_up' AND object_id=1") == expect_photos
        rows = [r[0] for r in conn.execute("SELECT storage_key FROM attachments ORDER BY id")]
        assert rows == [f"2026/10/30/photo{i}.jpg" for i in range(expect_photos)], rows
    assert q("SELECT COUNT(*) FROM tags") == 1
    assert q("SELECT COUNT(*) FROM customer_tags") == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "follow_ups_new" not in tables and "attachments_new" not in tables, tables
    assert not conn.execute("PRAGMA foreign_key_check").fetchall(), "外键孤儿"
    assert q("SELECT user_version FROM pragma_user_version") == 2
    conn.close()


def main() -> int:
    total = len(mig.STATEMENTS)
    print(f"语句总数 {total}")

    # ---------- A. 中断点扫描（无照片）----------
    cuts = sorted({0, 1, 5, 10, 20, 30, 40, 45, 48, 50, 52, 54, 56, 58, total})
    for cut in cuts:
        p = HERE / "int.db"
        fresh_copy(p)
        run_partial(p, cut)
        try:
            mig.apply(p, backup=False, verbose=False)
            state(p, 0)
        except Exception as exc:  # noqa: BLE001
            print(f"✗ 中断点 {cut} 未收敛: {exc}")
            raise
    print(f"✓ 中断点扫描全部收敛：{len(cuts)} 个切点 × 重跑 = 数据与结构一致")

    # ---------- B. attachments 有存量行 ----------
    p = HERE / "int_photos.db"
    fresh_copy(p, with_photos=4)
    mig.apply(p, backup=False, verbose=False)
    state(p, 4)
    print("✓ attachments 4 行存量：重建后 0 丢失，object_type/object_id 自动补齐")

    # ---------- C. 有照片 + 中断 ----------
    p = HERE / "int_photos_cut.db"
    fresh_copy(p, with_photos=4)
    run_partial(p, 52)          # 复制完但未 DROP 的中间态
    mig.apply(p, backup=False, verbose=False)
    state(p, 4)
    print("✓ 有照片 + 中断在重建中途：重跑收敛，4 行照片不丢")

    # ---------- D. 重复跑 3 次不漂移 ----------
    for _ in range(3):
        mig.apply(p, backup=False, verbose=False)
    state(p, 4)
    print("✓ 连续重跑 3 次：幂等、无漂移")
    return 0


if __name__ == "__main__":
    sys.exit(main())