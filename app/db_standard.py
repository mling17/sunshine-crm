"""数据库通用审计列与软删除约定。

所有业务表都保留既有 ``created_at`` / ``updated_at`` 以保证接口兼容，同时补齐：

- ``create_time`` / ``update_time``：标准审计时间；
- ``is_delete``：0 = 有效，1 = 已软删除。

新写入由触发器自动维护标准时间列，业务代码无需依赖旧列也能得到一致数据。
"""

from __future__ import annotations

import sqlite3


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote(table)})")}


def _tables(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name"
        )
    ]


def ensure_standard_columns(conn: sqlite3.Connection) -> None:
    """幂等补齐所有表的审计列、回填存量数据并安装维护触发器。"""
    for table in _tables(conn):
        table_sql = _quote(table)
        columns = _columns(conn, table)

        if "create_time" not in columns:
            conn.execute(
                f"ALTER TABLE {table_sql} ADD COLUMN create_time TEXT NOT NULL DEFAULT ''"
            )
            columns.add("create_time")
        if "update_time" not in columns:
            conn.execute(
                f"ALTER TABLE {table_sql} ADD COLUMN update_time TEXT NOT NULL DEFAULT ''"
            )
            columns.add("update_time")
        if "is_delete" not in columns:
            conn.execute(
                f"ALTER TABLE {table_sql} ADD COLUMN is_delete INTEGER NOT NULL DEFAULT 0"
            )
            columns.add("is_delete")

        create_expr = (
            f"COALESCE(NULLIF(created_at, ''), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
            if "created_at" in columns
            else "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
        )
        update_expr = (
            f"COALESCE(NULLIF(updated_at, ''), NULLIF(created_at, ''),"
            " strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
            if "updated_at" in columns and "created_at" in columns
            else (
                f"COALESCE(NULLIF(created_at, ''), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
                if "created_at" in columns
                else "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
            )
        )
        conn.execute(
            f"UPDATE {table_sql} SET"
            f" create_time = CASE WHEN create_time = '' THEN {create_expr} ELSE create_time END,"
            f" update_time = CASE WHEN update_time = '' THEN {update_expr} ELSE update_time END,"
            " is_delete = COALESCE(is_delete, 0)"
            " WHERE create_time = '' OR update_time = '' OR is_delete IS NULL"
        )

        insert_trigger = _quote(f"trg_std_{table}_ai")
        update_trigger = _quote(f"trg_std_{table}_au")
        conn.execute(f"DROP TRIGGER IF EXISTS {insert_trigger}")
        conn.execute(f"DROP TRIGGER IF EXISTS {update_trigger}")
        conn.execute(
            f"""
            CREATE TRIGGER {insert_trigger}
            AFTER INSERT ON {table_sql}
            BEGIN
              UPDATE {table_sql}
              SET create_time = CASE
                    WHEN create_time = '' THEN {create_expr.replace('created_at', 'NEW.created_at')}
                    ELSE create_time END,
                  update_time = CASE
                    WHEN update_time = '' THEN {update_expr.replace('created_at', 'NEW.created_at').replace('updated_at', 'NEW.updated_at')}
                    ELSE update_time END
              WHERE rowid = NEW.rowid;
            END
            """
        )
        conn.execute(
            f"""
            CREATE TRIGGER {update_trigger}
            AFTER UPDATE ON {table_sql}
            WHEN NEW.update_time = OLD.update_time
            BEGIN
              UPDATE {table_sql}
              SET update_time = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
              WHERE rowid = NEW.rowid;
            END
            """
        )


def ensure_active_lead_phone_unique(conn: sqlite3.Connection) -> None:
    """电话是线索表的唯一业务键；软删除行不占用该号码。"""
    conn.execute("DROP INDEX IF EXISTS uq_customers_phone_active")
    for table, index in (("leads", "uq_leads_phone_active"),):
        if table not in _tables(conn):
            continue
        duplicates = conn.execute(
            f"""
            SELECT phone, COUNT(*) AS n, GROUP_CONCAT(id) AS ids
            FROM {_quote(table)}
            WHERE phone IS NOT NULL AND TRIM(phone) <> '' AND is_delete = 0
            GROUP BY phone
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        if duplicates:
            detail = "；".join(
                f"{row['phone']}（ID {row['ids']}）" for row in duplicates[:10]
            )
            raise RuntimeError(f"{table}.phone 存在重复，无法建立唯一索引：{detail}")
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {index}"
            f" ON {_quote(table)}(phone)"
            " WHERE phone IS NOT NULL AND TRIM(phone) <> '' AND is_delete = 0"
        )
