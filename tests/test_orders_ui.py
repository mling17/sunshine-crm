"""Static regression checks for the orders list shell (Ticket #12)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OrdersListShellUiTest(unittest.TestCase):
    """Ticket #12：订单列表接入共享列表外壳（三态排序表头 + 页码按钮 + 每页条数），
    状态页签与分页排序全部交给服务端，状态写 `#/orders` hash URL。"""

    def setUp(self):
        self.js = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.html = (ROOT / "static/index.html").read_text(encoding="utf-8")

    def test_sortable_columns_and_computed_not(self):
        for key in ("order_name", "customer", "product", "total",
                    "logistics", "status", "created_at"):
            with self.subTest(key=key):
                self.assertIn("sortKey: '" + key + "'", self.js)
        # 已收/未收是计算列，操作列不参与排序
        for title in ("已收", "未收", "操作"):
            with self.subTest(title=title):
                start = self.js.index("{ title: '" + title + "'")
                seg = self.js[start:self.js.index("render:", start)]
                self.assertNotIn("sortKey", seg)

    def test_sort_keys_whitelist_matches_backend(self):
        start = self.js.index("var ORDER_SORT_KEYS")
        seg = self.js[start:self.js.index("];", start)]
        for key in ("order_name", "customer", "product", "total",
                    "logistics", "status", "created_at"):
            with self.subTest(key=key):
                self.assertIn("'" + key + "'", seg)

    def test_status_tabs_kept_and_sync_state(self):
        # 状态 Tab 保留（含 pending_confirmation → pending_payment 归一），切页签走统一状态入口（回第 1 页）
        for marker in ("orderVisibleStatuses()", "data-status",
                       "updateOrderListState(root, { status:"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_list_state_kept_in_hash_url_with_filters(self):
        for marker in (
            "query.get('status')",
            "query.get('customer_id')",
            "query.get('page')",
            "query.get('size')",
            "query.get('sort')",
            "query.get('order')",
            "history.replaceState",
            "p.set('status'",
            "p.set('customer_id'",
            "p.set('page'",
            "p.set('size'",
            "p.set('sort'",
            "p.set('order'",
            "#/orders?",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.js)

    def test_sort_size_tab_change_resets_page_to_1(self):
        # 除翻页（patch.page）外，改条数/排序/状态页签都回第 1 页
        self.assertIn("patch.page === undefined", self.js)
        self.assertIn("next.page = 1;", self.js)

    def test_uses_shell_pager_and_binding(self):
        self.assertIn("listPagerHtml(res)", self.js)
        self.assertIn("bindListShell($('#orderShell', root)", self.js)
        self.assertIn("cycleSortOrder(order)", self.js)
        self.assertIn("dataTable([", self.js)
        # 旧的本地 pagerHtml 必须移除（pagerHtml 对本视图本就未定义，是潜在 ReferenceError）
        self.assertIsNone(re.search(r"(?<!list)pagerHtml\(", self.js))
        # 固定 20 条的 PAGE_SIZE 不再使用（\b 排除 LIST_PAGE_SIZES）
        self.assertIsNone(re.search(r"\bPAGE_SIZE\b", self.js))

    def test_cache_buster_bumped(self):
        self.assertIn("/crm/views/orders.js?v=20261119carrier-items1", self.html)
        self.assertNotIn("orders.js?v=20261118order-list-shell1", self.html)


if __name__ == "__main__":
    unittest.main()
