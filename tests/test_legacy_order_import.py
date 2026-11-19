from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from tests._util import ApiTestCase
from app.db import db_conn
from app.legacy_order_import import IMPORT_TAG, run_import


def make_order_workbook(path: Path, *, a1: str = "普通平放普通把手天窗下单表") -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = a1
    ws["A2"] = "收货人+电话：孙文涛  199 1345 5558"
    ws["A3"] = "收货地址："
    ws["B3"] = "河南省信阳市淮滨县创新鸿泰两千家 包邮"
    ws["A4"] = "下单日期："
    ws["B4"] = "2026.11.19"
    ws["E4"] = "出货日期："
    ws["G4"] = "11月24日"
    ws["A5"] = "序号"
    ws["B5"] = "产品名称"
    ws["C5"] = "加工尺寸mm"
    ws["E5"] = "数量"
    ws["F5"] = "单价"
    ws["G5"] = "金额"
    ws["H5"] = "制作具体要求"
    ws["C6"] = "宽/mm"
    ws["D6"] = "高/mm"
    ws["A7"] = 1
    ws["B7"] = "洞口尺寸"
    ws["E7"] = 1
    ws["F7"] = 300
    ws["G7"] = 300
    ws["H7"] = "把手"
    ws["I7"] = "普通把手"
    ws["B8"] = "框制作尺寸"
    ws["C8"] = 815
    ws["D8"] = 815
    ws["B9"] = "扇制作尺寸"
    ws["C9"] = 820
    ws["D9"] = 817
    ws["H9"] = "颜色"
    ws["I9"] = "灰色"
    ws["B10"] = "玻璃尺寸"
    ws["C10"] = 693
    ws["D10"] = 690
    ws["H10"] = "气撑"
    ws["I10"] = "带，开启80度"
    ws["A11"] = "合计"
    ws["G11"] = 300
    ws["A21"] = "制单员："
    ws["B21"] = "刘晓寒"
    ws["F21"] = "销售员："
    ws["G21"] = "刘晓寒"
    wb.save(path)


class LegacyOrderImportTest(ApiTestCase):
    def _run(self, source: Path, root: Path, *, dry_run: bool = False):
        return run_import(
            source,
            dry_run=dry_run,
            recursive=False,
            error_dir=root / "errors",
            manifest_path=root / "manifest.json",
        )

    def test_commit_creates_full_history_chain(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "2026.11.19+孙文涛+刘晓寒+普通平放普通把手下单表.xlsx"
            make_order_workbook(source)

            result = self._run(source, root, dry_run=False)
            self.assertEqual(result["imported"], 1, result)
            self.assertEqual(result["failed"], 0, result)

            with db_conn() as conn:
                customer = conn.execute(
                    "SELECT * FROM customers WHERE phone = ? AND is_delete = 0",
                    ("19913455558",),
                ).fetchone()
                self.assertIsNotNone(customer)
                order = conn.execute(
                    "SELECT * FROM orders ORDER BY id DESC LIMIT 1"
                ).fetchone()
                self.assertEqual(order["status"], "completed")
                self.assertEqual(order["amount"], 300)
                self.assertEqual(order["deposit_paid"], 300)
                self.assertEqual(order["balance_paid"], 0)
                self.assertIsNone(order["note"])
                self.assertEqual(order["receiver_name"], "孙文涛")
                self.assertEqual(order["created_at"], "2026-11-19T00:00:00")
                self.assertEqual(order["completed_at"], "2026-11-24T00:00:00")

                quote = conn.execute(
                    "SELECT * FROM deal_quotes WHERE id = ?", (order["quote_id"],)
                ).fetchone()
                self.assertEqual(quote["status"], "confirmed")
                quote_item = conn.execute(
                    "SELECT * FROM quote_items WHERE quote_id = ?", (quote["id"],)
                ).fetchone()
                self.assertTrue(quote_item["form_storage_key"])
                self.assertIn("框制作尺寸 815×815", quote_item["spec"])

                tag = conn.execute(
                    "SELECT 1 FROM deal_tags dt JOIN tags t ON t.id = dt.tag_id"
                    " WHERE dt.deal_id = ? AND t.name = ? AND dt.is_delete = 0",
                    (order["deal_id"], IMPORT_TAG),
                ).fetchone()
                self.assertIsNotNone(tag)

                attach = conn.execute(
                    "SELECT * FROM attachments WHERE object_type = 'order_confirmation'"
                    " AND object_id = ? AND is_delete = 0",
                    (order["id"],),
                ).fetchone()
                self.assertIsNotNone(attach)
                self.assertEqual(attach["storage_key"], quote_item["form_storage_key"])

                log = conn.execute(
                    "SELECT * FROM order_status_log WHERE order_id = ?", (order["id"],)
                ).fetchone()
                self.assertEqual(log["to_status"], "completed")

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["entries"]), 1)

    def test_dry_run_does_not_write_and_copies_problem_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "bad.xlsx"
            make_order_workbook(source, a1="不存在的产品")

            result = self._run(source, root, dry_run=True)
            self.assertEqual(result["planned"], 0)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["errors"][0]["code"], "product_not_found")

            with db_conn() as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM customers WHERE phone = ?", ("19913455558",)).fetchone()[0],
                    0,
                )

            run_dir = Path(result["run_dir"])
            self.assertTrue((run_dir / "errors.csv").exists())
            self.assertTrue((run_dir / "summary.json").exists())
            self.assertTrue((run_dir / "files" / "bad.xlsx").exists())

    def test_same_sha_second_run_is_problem_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "same.xlsx"
            make_order_workbook(source)

            first = self._run(source, root, dry_run=False)
            second = self._run(source, root, dry_run=False)
            self.assertEqual(first["imported"], 1, first)
            self.assertEqual(second["imported"], 0, second)
            self.assertEqual(second["failed"], 1, second)
            self.assertEqual(second["errors"][0]["code"], "duplicate_sha256")

            with db_conn() as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1
                )

    def test_duplicate_customer_phone_aborts_whole_batch(self):
        with db_conn() as conn:
            now = "2026-11-19T00:00:00"
            for name in ("甲", "乙"):
                conn.execute(
                    "INSERT INTO customers (name, phone, created_at, updated_at)"
                    " VALUES (?, '19913455558', ?, ?)",
                    (name, now, now),
                )

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "same-phone.xlsx"
            make_order_workbook(source)
            result = self._run(source, root, dry_run=False)
            self.assertTrue(result["duplicate_customer_phones"], result)
            with db_conn() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
