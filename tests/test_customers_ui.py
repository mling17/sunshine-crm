"""Static regression checks for the customers list shell (Ticket #10)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CustomersListShellUiTest(unittest.TestCase):
    """Ticket #10：客户列表接入共享列表外壳（三态排序表头 + 页码按钮 + 每页条数）。"""

    def setUp(self):
        self.js = (ROOT / "static/views/customers.js").read_text(encoding="utf-8")
        self.shared = (ROOT / "static/views/shared.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_six_columns_sortable_and_others_not(self):
        for key in ("'name'", "'type'", "'location'", "'intent'", "'last_follow'", "'created_at'"):
            with self.subTest(key=key):
                self.assertIn("sortKey: " + key, self.js)
        for col in (
            "{ title: '标签'",
            "{ title: '微信号'",
            "{ title: '商机'",
            "{ title: '订单'",
            "{ title: '累计成交'",
            "{ title: '操作'",
        ):
            with self.subTest(col=col):
                start = self.js.index(col)
                seg = self.js[start:self.js.index("},", start)]
                self.assertNotIn("sortKey", seg)

    def test_last_follow_column_renders_value(self):
        start = self.js.index("{ title: '上次跟进'")
        seg = self.js[start:self.js.index("},", start)]
        self.assertIn("sortKey: 'last_follow'", seg)
        self.assertIn("c.last_follow", seg)
        self.assertIn("fmtDateTime(c.last_follow)", seg)

    def test_list_state_kept_in_hash_url(self):
        for marker in (
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('sort'",
            "p.set('order'",
            "#/customers?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_or_size_change_resets_page_to_1(self):
        self.assertIn("patch.size !== undefined || patch.sort !== undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_filter_change_resets_page_to_1_without_rerender(self):
        for marker in (
            "updateCustomerListState(root, { page: 1 });",
            "history.replaceState",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#custShell', root)", self.js)
        self.assertNotIn("pagerHtml(res)", self.js)
        self.assertNotIn("pagerEl.onclick", self.js)
        self.assertNotIn("function pagerHtml", self.js, "客户页本地 pagerHtml 必须移除")

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
