"""SQLite 连接助手（raw sqlite3，不上 ORM）。

用法::

    from app.db import db_conn

    with db_conn() as conn:
        conn.execute("INSERT ...", (...))
    # 正常退出自动 commit，异常自动 rollback，无论如何都 close

单用户场景：每次操作开一个连接、用完即关，不维护连接池。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

from app.config.settings import settings

DBPath = Union[str, Path, None]


def connect(db_path: DBPath = None) -> sqlite3.Connection:
    """打开连接：Row 取值、外键生效、父目录按需创建。"""
    path = Path(db_path) if db_path else settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    # SQLite 外键默认关闭，必须逐连接打开，否则 ON DELETE CASCADE 不生效
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_conn(db_path: DBPath = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
