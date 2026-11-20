"""Static regression checks for the deals list shell (Ticket #13)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DealsListShellUiTest(unittest.TestCase):
    """Ticket #13：商机列表接入共享列表外壳（三态排序表头 + 页码按钮 + 每页条数）。"""

    def setUp(self):
        self.js = (ROOT / "static/views/deals.js").read_text(encoding="utf-8")
        self.html = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_sortable_columns_and_computed_columns_not(self):
        # 首列「商机名称」已把客户名作为副标题合并展示，客户不再单独成列
        for key in (
            "'title'", "'product'", "'model'", "'drive_type'",
            "'size'", "'amount'", "'stage'", "'updated_at'",
        ):
            with self.subTest(key=key):
                self.assertIn("sortKey: " + key, self.js)
        for col in ("{ title: '操作'"):
            with self.subTest(col=col):
                start = self.js.index(col)
                seg = self.js[start:self.js.index("},", start)]
                self.assertNotIn("sortKey", seg)

    def test_deal_sort_keys_cover_whitelist(self):
        start = self.js.index("var DEAL_SORT_KEYS")
        seg = self.js[start:self.js.index("];", start)]
        for key in ("title", "customer", "product", "model", "drive_type", "size", "amount", "stage", "updated_at"):
            with self.subTest(key=key):
                self.assertIn("'" + key + "'", seg)

    def test_list_state_kept_in_hash_url_with_stage(self):
        for marker in (
            "query.get('stage')",
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('stage'",
            "p.set('page'",
            "p.set('size'",
            "p.set('sort'",
            "p.set('order'",
            "#/deals?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_size_stage_change_resets_page_to_1(self):
        self.assertIn("patch.size !== undefined || patch.sort !== undefined", self.js)
        self.assertIn("patch.stage !== undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#dealShell', root)", self.js)
        self.assertIn("cycleSortOrder(order)", self.js)
        self.assertIn("dataTable([", self.js)
        # 旧的整表加载 + 本地排序必须移除
        self.assertNotIn(".slice().sort(function", self.js)

    def test_api_call_sends_page_size_sort_order(self):
        start = self.js.index("function loadDeals")
        seg = self.js[start:]
        for marker in ("params.set('page'", "params.set('size'", "params.set('sort'", "params.set('order'"):
            with self.subTest(marker=marker):
                self.assertIn(marker, seg)

    def test_cache_buster_bumped(self):
        self.assertIn("/crm/views/deals.js?v=20261120deal-title1", self.html)
        self.assertNotIn("deals.js?v=20261119review-fixes1", self.html)

    def test_sortable_header_and_pager_styles(self):
        for selector in (
            "th.sortable",
            ".sort-arrow",
            ".list-pager",
            ".list-pager-pages",
            ".pager-page.active",
            ".list-pager-size",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css)


if __name__ == "__main__":
    unittest.main()
