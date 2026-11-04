"""SQLite / MySQL 连接助手（raw SQL，不上 ORM）。

用法::

    from app.db import db_conn

    with db_conn() as conn:
        conn.execute("INSERT ...", (...))
    # 正常退出自动 commit，异常自动 rollback，无论如何都 close

通过 ``CRM_DB_ENGINE=sqlite|mysql`` 切换。业务 SQL 保持 SQLite 写法，
MySQL 适配层负责处理占位符、冲突写入、时间函数以及 ``lastrowid`` 差异。
单用户场景：每次操作开一个连接、用完即关，不维护连接池。
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Union

import sqlglot
from sqlglot import exp

from app.config.settings import settings

DBPath = Union[str, Path, None]

try:
    import pymysql
    from pymysql.cursors import DictCursor

    DatabaseError = (sqlite3.Error, pymysql.MySQLError)
    IntegrityError = (sqlite3.IntegrityError, pymysql.err.IntegrityError)
except ImportError:  # SQLite 模式仍可在未安装 MySQL 驱动时运行
    pymysql = None
    DictCursor = None
    DatabaseError = sqlite3.Error
    IntegrityError = sqlite3.IntegrityError


class MySQLRow(Mapping[str, Any]):
    """同时支持 ``row["name"]`` 和 ``row[0]``，对齐 sqlite3.Row 的调用习惯。"""

    __slots__ = ("_data", "_keys")

    def __init__(self, data: Mapping[str, Any]):
        self._data = dict(data)
        self._keys = tuple(self._data)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._data[self._keys[key]]
        return self._data[key]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __repr__(self) -> str:
        return f"MySQLRow({self._data!r})"


class MySQLCursor:
    """最小 DB-API 游标适配；业务代码只依赖 execute/fetch*/lastrowid。"""

    def __init__(self, cursor: Any):
        self._cursor = cursor
        self.lastrowid = 0

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def description(self):
        return self._cursor.description

    def _row(self, row: Any) -> MySQLRow | None:
        return MySQLRow(row) if isinstance(row, dict) else row

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchmany(self, size: int | None = None):
        if size is None:
            return [self._row(row) for row in self._cursor.fetchmany()]
        return [self._row(row) for row in self._cursor.fetchmany(size)]

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    def close(self) -> None:
        self._cursor.close()


_ON_CONFLICT = re.compile(
    r"\bON\s+CONFLICT\s*\([^)]*\)\s+DO\s+UPDATE\s+SET\b",
    flags=re.IGNORECASE | re.DOTALL,
)
_EXCLUDED_COLUMN = re.compile(
    r"\bexcluded\.([A-Za-z_][A-Za-z0-9_]*)",
    flags=re.IGNORECASE,
)


def _set_expr(node: exp.Expression, value: exp.Expression) -> None:
    if node.parent is None:
        raise ValueError("无法替换根表达式")
    node.replace(value)


def _anonymous(node: exp.Expression, name: str, *args: exp.Expression) -> exp.Expression:
    return exp.Anonymous(this=name, expressions=list(args))


def _mysql_var(sql: str) -> exp.Expression:
    """生成一段MySQL表达式；Var 不会被 MySQL 生成器改写函数参数顺序。"""
    return exp.Var(this=sql)


def _render_mysql(node: exp.Expression) -> str:
    return node.sql(dialect="mysql", identify=True)


def _date_expr(node: exp.Expression) -> exp.Expression:
    """把 SQLite ``date(...)`` 转成 MySQL 可执行表达式。"""
    if isinstance(node, exp.Anonymous) and node.name.upper() == "DATE":
        args = list(node.expressions)
        if args:
            first = args[0]
            if isinstance(first, exp.Literal) and not first.is_string:
                first = exp.var(str(first.this))
            modifiers = [
                str(arg.this).lower()
                for arg in args[1:]
                if isinstance(arg, exp.Literal) and arg.is_string
            ]
            if isinstance(first, exp.Literal) and first.is_string and first.this.lower() == "now":
                if "localtime" not in modifiers:
                    return exp.CurrentDate()
                current_sql = "CURRENT_DATE"
                for modifier in modifiers:
                    if modifier == "localtime":
                        continue
                    match = re.fullmatch(r"([+-])(\d+)\s+(day|month|year)s?", modifier)
                    if match:
                        fn = "DATE_SUB" if match.group(1) == "-" else "DATE_ADD"
                        current_sql = (
                            f"{fn}({current_sql}, INTERVAL {int(match.group(2))} "
                            f"{match.group(3).upper()})"
                        )
                    elif modifier == "start of month":
                        current_sql = f"DATE_FORMAT({current_sql}, '%Y-%m-01')"
                    elif modifier == "start of year":
                        current_sql = f"DATE_FORMAT({current_sql}, '%Y-01-01')"
                return _mysql_var(current_sql)
            return exp.Date(this=first)
    if isinstance(node, exp.Date):
        return node
    return exp.Date(this=node)


def _convert_sqlite_temporal(node: exp.Expression) -> exp.Expression | None:
    """单个 SQLite 时间函数的 MySQL 等价表达式；无法识别返回 None。"""
    if not isinstance(node, exp.Anonymous):
        return None
    name = node.name.upper()
    args = list(node.expressions)

    if name == "DATE":
        return _date_expr(node)

    if name == "DATETIME" and args:
        source = args[0]
        localized = any(
            isinstance(arg, exp.Literal)
            and arg.is_string
            and arg.this.lower() == "localtime"
            for arg in args[1:]
        )
        is_now = (
            isinstance(source, exp.Literal)
            and source.is_string
            and source.this.lower() == "now"
        )
        if is_now:
            modifiers = [
                str(arg.this).lower()
                for arg in args[1:]
                if isinstance(arg, exp.Literal) and arg.is_string
            ]
            if "start of month" in modifiers:
                return _mysql_var("DATE_FORMAT(CURRENT_TIMESTAMP, '%Y-%m-01 00:00:00')")
            return _mysql_var("CURRENT_TIMESTAMP()" if localized else "UTC_TIMESTAMP()")
        if localized:
            return _mysql_var(
                f"CONVERT_TZ({_render_mysql(source)}, '+00:00', '+08:00')"
            )
        return source

    if name == "STRFTIME" and len(args) >= 2:
        fmt_node, source = args[0], args[1]
        fmt = str(fmt_node.this) if isinstance(fmt_node, exp.Literal) else ""
        is_now = (
            isinstance(source, exp.Literal)
            and source.is_string
            and source.this.lower() == "now"
        )
        localized = any(
            isinstance(arg, exp.Literal)
            and arg.is_string
            and arg.this.lower() == "localtime"
            for arg in args[2:]
        )
        if is_now:
            clock_sql = "CURRENT_TIMESTAMP()" if localized else "UTC_TIMESTAMP()"
            return _mysql_var(
                f"DATE_FORMAT({clock_sql}, '{fmt.replace('%H:%M:%S', '%H:%i:%s')}')"
            )
        return _mysql_var(
            f"DATE_FORMAT({_render_mysql(source)}, "
            f"'{fmt.replace('%H:%M:%S', '%H:%i:%s')}')"
        )

    return None


def _date_for_datediff(node: exp.Expression) -> exp.Expression:
    if isinstance(node, exp.Anonymous) and node.name.upper() == "DATE":
        return _date_expr(node)
    if isinstance(node, exp.Date):
        return node
    return exp.Date(this=node)


@lru_cache(maxsize=512)
def _translate_mysql(sql: str) -> str:
    """把业务层 SQLite SQL 转成 MySQL 8 SQL，并对生成的 SQL 做缓存。"""
    source = re.sub(
        r"\blast_insert_rowid\s*\(\s*\)",
        "LAST_INSERT_ID()",
        sql,
        flags=re.IGNORECASE,
    )
    source = _ON_CONFLICT.sub("ON CONFLICT(__crm_keys__) DO UPDATE SET", source)
    source = _EXCLUDED_COLUMN.sub(r"excluded.\1", source)
    trees = sqlglot.parse(source, read="sqlite")
    output: list[str] = []
    for tree in trees:
        # MySQL 要求 FROM/JOIN 后的派生表必须有别名，SQLite 不要求。
        for index, subquery in enumerate(list(tree.find_all(exp.Subquery)), start=1):
            if not subquery.alias and isinstance(subquery.parent, (exp.From, exp.Join)):
                subquery.set("alias", exp.TableAlias(this=exp.to_identifier(f"_sq{index}")))

        for insert in list(tree.find_all(exp.Insert)):
            alternative = insert.args.get("alternative")
            if alternative is not None and str(alternative).upper() == "IGNORE":
                insert.set("alternative", None)
                insert.set("ignore", True)
            conflict = insert.args.get("conflict")
            if isinstance(conflict, exp.OnConflict):
                conflict.set("duplicate", True)
                conflict.set("action", exp.var("UPDATE"))
                conflict.set("conflict_keys", None)
                for column in list(conflict.find_all(exp.Column)):
                    if column.table.lower() == "excluded":
                        _set_expr(
                            column,
                            _anonymous(
                                column,
                                "VALUES",
                                exp.Identifier(this=column.name),
                            ),
                        )

        # julianday(a)-julianday(b) 只用于“相差几天”，直接换成 DATEDIFF。
        for subtract in list(tree.find_all(exp.Sub)):
            left, right = subtract.this, subtract.expression
            if (
                isinstance(left, exp.Anonymous)
                and left.name.lower() == "julianday"
                and isinstance(right, exp.Anonymous)
                and right.name.lower() == "julianday"
                and left.expressions
                and right.expressions
            ):
                _set_expr(
                    subtract,
                    _mysql_var(
                        "DATEDIFF("
                        f"{_render_mysql(_date_for_datediff(left.expressions[0]))}, "
                        f"{_render_mysql(_date_for_datediff(right.expressions[0]))})"
                    ),
                )

        for date_func in list(tree.find_all(exp.Date)):
            if isinstance(date_func.this, exp.Anonymous) and date_func.this.name.upper() == "DATE":
                _set_expr(date_func, _date_expr(date_func.this))

        for time_to_str in list(tree.find_all(exp.TimeToStr)):
            fmt_node = time_to_str.args.get("format")
            fmt = str(fmt_node.this) if isinstance(fmt_node, exp.Literal) else ""
            source = time_to_str.this
            if (
                isinstance(source, exp.TsOrDsToTimestamp)
                and isinstance(source.this, exp.Literal)
                and source.this.is_string
                and source.this.this.lower() == "now"
            ):
                value = (
                    f"DATE_FORMAT(UTC_TIMESTAMP(), "
                    f"'{fmt.replace('%H:%M:%S', '%H:%i:%s')}')"
                )
            else:
                value = (
                    f"DATE_FORMAT({_render_mysql(source)}, "
                    f"'{fmt.replace('%H:%M:%S', '%H:%i:%s')}')"
                )
            _set_expr(time_to_str, _mysql_var(value))

        # 使用快照，避免在遍历过程中替换父子节点导致漏转。
        for func in list(tree.find_all(exp.Anonymous)):
            converted = _convert_sqlite_temporal(func)
            if converted is not None:
                _set_expr(func, converted)

        output.append(tree.sql(dialect="mysql", identify=True))
    return ";\n".join(output)


class MySQLConnection:
    """PyMySQL 连接适配层，接口覆盖当前项目使用的 sqlite3 子集。"""

    backend = "mysql"

    def __init__(self):
        if pymysql is None:
            raise RuntimeError("使用 MySQL 需要安装 PyMySQL")
        self._conn = pymysql.connect(
            host=settings.CRM_MYSQL_HOST,
            port=settings.CRM_MYSQL_PORT,
            user=settings.CRM_MYSQL_USER,
            password=settings.CRM_MYSQL_PASSWORD,
            database=settings.CRM_MYSQL_DATABASE,
            charset=settings.CRM_MYSQL_CHARSET,
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
            ssl_disabled=settings.CRM_MYSQL_SSL_DISABLED,
            init_command="SET SESSION time_zone = '+08:00'",
        )

    def execute(self, sql: str, params: Any = None) -> MySQLCursor:
        statement = sql.strip()
        statement = re.sub(
            r"\blast_insert_rowid\s*\(\s*\)",
            "LAST_INSERT_ID()",
            statement,
            flags=re.IGNORECASE,
        )
        if re.fullmatch(r"BEGIN\s+IMMEDIATE", statement, flags=re.IGNORECASE):
            cursor = self._conn.cursor()
            return MySQLCursor(cursor)

        table_match = re.search(
            r"PRAGMA\s+table_info\s*\(\s*[`\"']?([A-Za-z0-9_]+)[`\"']?\s*\)",
            statement,
            flags=re.IGNORECASE,
        )
        if table_match:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT ORDINAL_POSITION - 1 AS cid, COLUMN_NAME AS name,"
                " DATA_TYPE AS type, IS_NULLABLE AS notnull,"
                " COLUMN_DEFAULT AS dflt_value, 0 AS pk"
                " FROM information_schema.COLUMNS"
                " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
                " ORDER BY ORDINAL_POSITION",
                (table_match.group(1),),
            )
            return MySQLCursor(cursor)

        if re.search(r"\bsqlite_master\b", statement, flags=re.IGNORECASE):
            match = re.search(
                r"type\s*=\s*'(table|trigger)'\s+AND\s+name\s*=\s*'([^']+)'",
                statement,
                flags=re.IGNORECASE,
            )
            cursor = self._conn.cursor()
            if match:
                object_type, name = match.groups()
                catalog = "TABLES" if object_type.lower() == "table" else "TRIGGERS"
                cursor.execute(
                    f"SELECT 1 FROM information_schema.{catalog}"
                    " WHERE TABLE_SCHEMA = DATABASE()"
                    " AND "
                    + ("TABLE_NAME" if catalog == "TABLES" else "TRIGGER_NAME")
                    + " = %s LIMIT 1",
                    (name,),
                )
            else:
                cursor.execute("SELECT 1 WHERE 0")
            return MySQLCursor(cursor)

        translated = _translate_mysql(statement)
        # PyMySQL 使用 %s 占位，SQL 中的 DATE_FORMAT 百分号也要转义。
        translated = translated.replace("%", "%%").replace("?", "%s")
        cursor = self._conn.cursor()
        args = () if params is None else params
        cursor.execute(translated, args)
        wrapped = MySQLCursor(cursor)
        wrapped.lastrowid = int(self._conn.insert_id() or 0)
        return wrapped

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def connect(db_path: DBPath = None) -> sqlite3.Connection | MySQLConnection:
    """按配置打开连接；显式传路径时始终使用 SQLite。"""
    if db_path is None and settings.CRM_DB_ENGINE == "mysql":
        return MySQLConnection()
    path = Path(db_path) if db_path else settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    # SQLite 外键默认关闭，必须逐连接打开，否则 ON DELETE CASCADE 不生效
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_conn(
    db_path: DBPath = None,
) -> Iterator[sqlite3.Connection | MySQLConnection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
