"""Static regression checks for the aftersales list shell (Ticket #11)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AftersalesListShellUiTest(unittest.TestCase):
    """Ticket #11：售后列表接入共享列表外壳（三态排序表头 + 页码按钮 + 每页条数），
    状态页签与分页排序全部交给服务端，状态写 `#/aftersales` hash URL。"""

    def setUp(self):
        self.js = (ROOT / "static/views/aftersales.js").read_text(encoding="utf-8")
        self.html = (ROOT / "static/index.html").read_text(encoding="utf-8")

    def test_sortable_columns_and_operations_not(self):
        for key in ("aftersale_no", "type", "order", "customer", "problem",
                    "status", "created_at"):
            with self.subTest(key=key):
                self.assertIn("sortKey: '" + key + "'", self.js)
        # 操作列不可排序
        start = self.js.index("{ title: '操作'")
        seg = self.js[start:self.js.index("], items", start)]
        self.assertNotIn("sortKey", seg)

    def test_sort_keys_whitelist_matches_backend(self):
        start = self.js.index("var AFTERSALE_SORT_KEYS")
        seg = self.js[start:self.js.index("];", start)]
        for key in ("aftersale_no", "type", "order", "customer", "problem",
                    "status", "created_at"):
            with self.subTest(key=key):
                self.assertIn("'" + key + "'", seg)

    def test_status_tabs_kept_and_sync_state(self):
        # 三态页签保留，切页签走统一状态入口（回第 1 页）
        for marker in ("['pending', '待处理']", "['processing', '处理中']",
                       "['done', '已完成']", "data-status",
                       "updateAftersaleListState(root, { status:"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_list_state_kept_in_hash_url_with_filters(self):
        for marker in (
            "query.get('status')",
            "query.get('order_id')",
            "query.get('customer_id')",
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('status'",
            "p.set('order_id'",
            "p.set('customer_id'",
            "p.set('page'",
            "p.set('size'",
            "p.set('sort'",
            "p.set('order'",
            "#/aftersales?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_size_filter_change_resets_page_to_1(self):
        # 除翻页（patch.page）外，改条数/排序/状态筛选都回第 1 页
        self.assertIn("patch.page === undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#asShell', root)", self.js)
        self.assertIn("cycleSortOrder(order)", self.js)
        self.assertIn("dataTable([", self.js)
        # 旧的本地 pagerHtml / 固定 PAGE_SIZE 必须移除（listPagerHtml 不算）
        self.assertIsNone(re.search(r"(?<!list)pagerHtml\(", self.js))
        # 固定 20 条的 PAGE_SIZE 不再使用（\b 排除 LIST_PAGE_SIZES）
        self.assertIsNone(re.search(r"\bPAGE_SIZE\b", self.js))

    def test_cache_buster_bumped(self):
        self.assertIn("/crm/views/aftersales.js?v=20261118aftersale-list-shell1", self.html)
        self.assertNotIn("aftersales.js?v=20261104lead1", self.html)


if __name__ == "__main__":
    unittest.main()
