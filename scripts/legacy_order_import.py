r"""CLI for importing legacy order-form workbooks.

Examples:
    py -3 scripts/legacy_order_import.py --source "E:\path\orders" --recursive
    py -3 scripts/legacy_order_import.py --source "E:\path\orders" --recursive --commit --env-file .local\crm.env
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env_file(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入 Sunshine CRM 历史下单表")
    parser.add_argument("--source", required=True, help="xlsx 文件或目录")
    parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    parser.add_argument("--commit", action="store_true", help="正式写入；默认只做 dry-run")
    parser.add_argument(
        "--error-dir",
        default=r"C:\Users\P0182449\Desktop\import_error",
        help="问题文件归档根目录",
    )
    parser.add_argument(
        "--manifest",
        default=r"C:\Users\P0182449\Desktop\legacy_order_import_manifest.json",
        help="成功导入幂等 manifest",
    )
    parser.add_argument("--env-file", help="读取 CRM_DB / CRM_UPLOADS 等配置的环境文件")
    parser.add_argument("--db", help="显式 SQLite 数据库路径；会覆盖 CRM_DB")
    parser.add_argument("--uploads", help="显式上传根目录；会覆盖 CRM_UPLOADS")
    args = parser.parse_args(argv)

    if args.env_file:
        load_env_file(Path(args.env_file))
    if args.db:
        os.environ["CRM_DB_ENGINE"] = "sqlite"
        os.environ["CRM_DB"] = args.db
    if args.uploads:
        os.environ["CRM_UPLOADS"] = args.uploads

    from app.legacy_order_import import run_import

    result = run_import(
        Path(args.source),
        dry_run=not args.commit,
        recursive=args.recursive,
        error_dir=Path(args.error_dir),
        manifest_path=Path(args.manifest),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if result.get("duplicate_customer_phones"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
