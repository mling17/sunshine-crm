#!/usr/bin/env python3
"""把已完成 V2.018 迁移的 SQLite 数据复制到 MySQL 8。

特性：
- 默认拒绝写入非空目标库，避免覆盖已有数据；
- ``--replace`` 才会清空目标业务表（仍然保留并重建代码定义的表结构）；
- 保留原主键、业务时间、软删除状态，按表校验源/目标行数；
- 只迁移数据库记录；``CRM_UPLOADS`` 下的附件由文档中的 rsync 步骤同步。

典型用法：
    CRM_DB=/opt/data/crm/crm.db \
    CRM_MYSQL_HOST=127.0.0.1 CRM_MYSQL_USER=crm \
    CRM_MYSQL_PASSWORD='...' CRM_MYSQL_DATABASE=sunshine_crm \
    python ops/migrate_sqlite_to_mysql.py
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

from app.config.settings import settings
from app.mysql_schema import TABLE_DDL, ensure_mysql_schema, _raw_connection


# 先写主档，再写关系与流水；没有外键，但该顺序便于失败时人工排查。
COPY_ORDER = (
    "users",
    "sessions",
    "customers",
    "customer_contacts",
    "customer_addresses",
    "tags",
    "customer_tags",
    "leads",
    "lead_tags",
    "carriers",
    "carrier_contacts",
    "products",
    "deals",
    "deal_items",
    "deal_tags",
    "follow_ups",
    "attachments",
    "orders",
    "order_items",
    "order_status_log",
    "deal_quotes",
    "quote_items",
    "aftersales",
    "aftersale_status_log",
    "follow_up_phrases",
    "dict_items",
    "import_log",
    "schema_migrations",
    "migration_clear_guard",
)


def _source_tables(source: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in source.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _source_columns(source: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in source.execute(f'PRAGMA table_info("{table}")')]


def _target_columns(target, table: str) -> list[str]:
    with target.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS"
            " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
            " AND EXTRA NOT LIKE '%%GENERATED%%'"
            " ORDER BY ORDINAL_POSITION",
            (table,),
        )
        return [str(row["name"]) for row in cursor.fetchall()]


def _target_counts(target) -> dict[str, int]:
    counts: dict[str, int] = {}
    with target.cursor() as cursor:
        for table in COPY_ORDER:
            if table not in TABLE_DDL:
                continue
            cursor.execute(f"SELECT COUNT(*) AS n FROM `{table}`")
            counts[table] = int(cursor.fetchone()["n"])
    return counts


def _clear_target(target) -> None:
    with target.cursor() as cursor:
        for table in reversed(COPY_ORDER):
            if table in TABLE_DDL:
                cursor.execute(f"DELETE FROM `{table}`")


def _copy_table(
    source: sqlite3.Connection,
    target,
    table: str,
    *,
    batch_size: int,
) -> tuple[int, int]:
    source_cols = _source_columns(source, table)
    target_cols = set(_target_columns(target, table))
    columns = [column for column in source_cols if column in target_cols]
    if not columns:
        raise RuntimeError(f"{table}: 源表与目标表没有共同字段")
    missing_required = {"create_time", "update_time", "is_delete"} - set(columns)
    if missing_required:
        raise RuntimeError(
            f"{table}: 源库缺少标准字段 {sorted(missing_required)}，"
            "请先用当前版本启动 SQLite，让 V2 迁移执行完成"
        )

    quoted_cols = ", ".join(f"`{column}`" for column in columns)
    source_sql = f'SELECT {quoted_cols} FROM "{table}"'
    target_sql = (
        f"INSERT INTO `{table}` ({quoted_cols})"
        f" VALUES ({', '.join(['%s'] * len(columns))})"
    )
    source_count = int(
        source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    )
    copied = 0
    cursor = source.execute(source_sql)
    with target.cursor() as target_cursor:
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            rows = [tuple(row) for row in rows]
            try:
                target_cursor.executemany(target_sql, rows)
            except Exception as exc:
                raise RuntimeError(f"{table}: 写入 MySQL 失败: {exc}") from exc
            copied += len(rows)
    if copied != source_count:
        raise RuntimeError(
            f"{table}: 读取行数不一致，源 {source_count} / 读取 {copied}"
        )
    return source_count, len(columns)


def _reset_auto_increment(target) -> None:
    with target.cursor() as cursor:
        for table in COPY_ORDER:
            if table not in TABLE_DDL:
                continue
            cursor.execute(
                "SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS"
                " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
                " AND EXTRA LIKE '%%auto_increment%%'",
                (table,),
            )
            if not cursor.fetchone():
                continue
            cursor.execute(f"SELECT COALESCE(MAX(`id`), 0) AS n FROM `{table}`")
            next_id = int(cursor.fetchone()["n"] or 0) + 1
            cursor.execute(f"ALTER TABLE `{table}` AUTO_INCREMENT = {next_id}")


def _validate(source: sqlite3.Connection, target, tables: Iterable[str]) -> None:
    target_counts = _target_counts(target)
    failures: list[str] = []
    for table in tables:
        source_count = int(
            source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        )
        target_count = target_counts[table]
        if source_count != target_count:
            failures.append(
                f"{table}: SQLite {source_count} 行 / MySQL {target_count} 行"
            )
    if failures:
        raise RuntimeError("迁移后行数校验失败：\n" + "\n".join(failures))


def migrate(
    source_path: Path,
    *,
    replace: bool,
    dry_run: bool,
    batch_size: int,
) -> dict[str, int]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite 文件不存在：{source_path}")

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        source_tables = _source_tables(source)
        tables = [table for table in COPY_ORDER if table in source_tables]
        required = {
            "users",
            "customers",
            "deals",
            "follow_ups",
            "products",
            "dict_items",
            "schema_migrations",
        }
        if missing := required - source_tables:
            raise RuntimeError(
                f"源库缺少核心表 {sorted(missing)}；请先在当前应用启动一次 SQLite"
            )
        version = source.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 'v2_018'"
        ).fetchone()
        if version is None:
            raise RuntimeError(
                "源库尚未完成 v2_018 迁移；请先用当前版本启动一次 SQLite"
            )

        counts = {
            table: int(source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
        }
        if dry_run:
            return counts

        ensure_mysql_schema()
        target = _raw_connection()
        try:
            existing = _target_counts(target)
            nonempty = {table: n for table, n in existing.items() if n > 0}
            if nonempty and not replace:
                raise RuntimeError(
                    "目标 MySQL 不是空库。为防止误覆盖，默认中止；"
                    "确认可清空后加 --replace。当前非空表："
                    + ", ".join(f"{k}={v}" for k, v in nonempty.items())
                )
            if replace:
                _clear_target(target)

            for table in tables:
                source_count, _ = _copy_table(
                    source, target, table, batch_size=batch_size
                )
                print(f"[copy] {table}: {source_count} rows")
            _reset_auto_increment(target)
            _validate(source, target, tables)
            target.commit()
        except BaseException:
            target.rollback()
            raise
        finally:
            target.close()
        return counts
    finally:
        source.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite → MySQL 8 数据迁移")
    parser.add_argument("--source", default=settings.CRM_DB, help="SQLite 文件路径")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="允许清空非空目标表；目标库名/账号来自 CRM_MYSQL_* 环境变量",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计源库，不写 MySQL")
    parser.add_argument("--batch-size", type=int, default=500, help="每批行数")
    args = parser.parse_args(argv)

    if args.batch_size <= 0:
        parser.error("--batch-size 必须大于 0")

    source_path = Path(args.source).expanduser().resolve()
    print(f"source={source_path}")
    print(f"target={settings.database_label}")
    try:
        counts = migrate(
            source_path,
            replace=args.replace,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = sum(counts.values())
    if args.dry_run:
        print(f"dry-run OK: {len(counts)} tables / {total} rows")
    else:
        print(f"migration OK: {len(counts)} tables / {total} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
