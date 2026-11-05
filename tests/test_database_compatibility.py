"""数据库方言适配的纯单元测试（不需要启动 MySQL 服务）。"""

from __future__ import annotations

import unittest

from app.config.settings import settings
from app.db import _translate_mysql
from app.mysql_schema import TABLE_DDL, table_ddl


class MySQLDialectTest(unittest.TestCase):
    def test_insert_ignore_is_translated(self):
        sql = _translate_mysql(
            "INSERT OR IGNORE INTO products (seed_key) VALUES (?)"
        )
        self.assertIn("INSERT IGNORE INTO", sql)

    def test_sqlite_upsert_and_excluded_are_translated(self):
        sql = _translate_mysql(
            "INSERT INTO dict_items (dict_code, key) VALUES (?, ?)"
            " ON CONFLICT(dict_code, key) DO UPDATE SET"
            " label = excluded.label, updated_at = datetime('now')"
        )
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)
        self.assertIn("VALUES(label)", sql)
        self.assertNotIn("excluded.", sql)
        self.assertIn("UTC_TIMESTAMP()", sql)

    def test_sqlite_time_functions_are_translated(self):
        sql = _translate_mysql(
            "SELECT"
            " CAST(julianday(date('now','localtime'))"
            " - julianday(date(created_at)) AS INTEGER),"
            " datetime(created_at, 'localtime'),"
            " date('now','localtime','start of month','-2 months')"
            " FROM customers"
        )
        self.assertIn("DATEDIFF(CURRENT_DATE, DATE(`created_at`))", sql)
        self.assertIn("CONVERT_TZ(`created_at`, '+00:00', '+08:00')", sql)
        self.assertIn(
            "DATE_SUB(DATE_FORMAT(CURRENT_DATE, '%Y-%m-01'), INTERVAL 2 MONTH)",
            sql,
        )
        self.assertNotIn("julianday", sql.lower())

    def test_derived_table_gets_mysql_alias(self):
        sql = _translate_mysql(
            "SELECT COUNT(*) FROM (SELECT customer_id FROM deals GROUP BY customer_id)"
        )
        self.assertRegex(sql, r"\) AS `_sq\d+`")

    def test_last_insert_rowid_is_translated(self):
        sql = _translate_mysql("SELECT last_insert_rowid()")
        self.assertIn("LAST_INSERT_ID()", sql)


class MySQLSchemaDefinitionTest(unittest.TestCase):
    def test_all_expected_tables_are_defined(self):
        expected = {
            "users",
            "sessions",
            "customers",
            "deals",
            "follow_ups",
            "attachments",
            "products",
            "orders",
            "order_items",
            "aftersales",
            "dict_items",
            "schema_migrations",
        }
        self.assertTrue(expected <= set(TABLE_DDL))
        self.assertNotIn("customer_contacts", TABLE_DDL)

    def test_every_table_has_standard_columns_and_no_foreign_keys(self):
        for statement in table_ddl():
            self.assertIn("`create_time`", statement)
            self.assertIn("`update_time`", statement)
            self.assertIn("`is_delete`", statement)
            self.assertNotIn("FOREIGN KEY", statement.upper())
            self.assertNotIn(" REFERENCES ", statement.upper())
            self.assertNotIn("AUTOINCREMENT", statement.upper())

    def test_mysql_uses_utf8mb4(self):
        for statement in table_ddl():
            self.assertIn("DEFAULT CHARSET=utf8mb4", statement)

    def test_database_label_never_contains_password(self):
        if settings.CRM_DB_ENGINE == "mysql":
            self.assertNotIn(settings.CRM_MYSQL_PASSWORD, settings.database_label)


if __name__ == "__main__":
    unittest.main()
