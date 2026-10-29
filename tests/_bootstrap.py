"""测试环境引导 —— 必须在 import app.* 之前完成。

铁律（见实施计划 §6）：
1. 测试一律指向临时库，默认 ``CRM_DB=/tmp/crm-t.db``、``CRM_UPLOADS=/tmp/crm-t-up``；
2. 一旦发现 ``CRM_DB`` 指向生产库 ``/opt/data/crm/crm.db``，直接抛错中止，
   绝不拿真实数据做测试（数据保护红线）。
3. ``app.config.settings`` 在 import 时即读取环境变量，所以本模块必须最先被 import。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

PROD_DB = Path("/opt/data/crm/crm.db").resolve()

TEST_DB = Path(os.environ.get("CRM_DB") or "/tmp/crm-t.db").expanduser()
TEST_UPLOADS = Path(os.environ.get("CRM_UPLOADS") or "/tmp/crm-t-up").expanduser()

if TEST_DB.resolve() == PROD_DB:
    raise RuntimeError(
        f"测试禁止使用生产库 {PROD_DB}，请把 CRM_DB 指到 /tmp 下的临时文件"
    )

os.environ["CRM_DB"] = str(TEST_DB)
os.environ["CRM_UPLOADS"] = str(TEST_UPLOADS)
os.environ.setdefault("ADMIN_USERNAME", "chen")
os.environ.setdefault("ADMIN_PASSWORD", "test123")


def reset_db() -> None:
    """删掉临时库与临时上传目录，让 lifespan 从零建表 + 建种子用户。"""
    TEST_DB.unlink(missing_ok=True)
    shutil.rmtree(TEST_UPLOADS, ignore_errors=True)


# 模块级只执行一次（import 缓存），保证每次跑测试都是干净的空库
reset_db()
