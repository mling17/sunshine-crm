"""Customer 360 overview and progressive timeline regression checks."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class Customer360UiTest(unittest.TestCase):
    def setUp(self):
        self.customers = (STATIC / "views/customers.js").read_text(encoding="utf-8")
        self.shared = (STATIC / "views/shared.js").read_text(encoding="utf-8")
        self.css = (STATIC / "customer-360.css").read_text(encoding="utf-8")
        self.polish_css = (STATIC / "ui-polish.css").read_text(encoding="utf-8")
        self.index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.sw = (STATIC / "sw.js").read_text(encoding="utf-8")

    def test_customer_list_name_cell_matches_lead_without_contact_prefix(self):
        self.assertIn("customerNameCellHtml(c)", self.customers)
        self.assertIn("c.primary_contact_name", self.customers)
        self.assertIn("c.primary_contact_phone", self.customers)
        self.assertIn("customerContactPhone(c)", self.customers)
        self.assertIn('class="lead-name-cell customer-name-cell"', self.customers)
        self.assertNotIn("联系人：", self.customers)
        self.assertNotIn("{ title: '联系方式'", self.customers)
        self.assertIn("api('/tags?limit=8')", self.customers)
        self.assertIn("'customer-table', 'customer-table-wrap'", self.customers)
        for selector in (
            ".table-wrap.customer-table-wrap",
            "table.data-table.customer-table",
            ".customer-name-cell",
            ".customer-repeat-badge",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.polish_css)

    def test_customer_detail_title_matches_lead_layout(self):
        detail = self.customers[self.customers.index("function viewCustomerDetail"):]
        for marker in (
            "lead-detail-title-main",
            "lead-detail-crumb",
            "lead-detail-title-line",
            "detail-title-tags",
            "detail-title-tag",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, detail)

    def test_customer_list_adds_order_count_before_closed_amount(self):
        list_source = self.customers[
            self.customers.index("function loadCustomers"):
            self.customers.index("function openCustomerDealModal")
        ]
        self.assertIn("{ title: '订单'", list_source)
        self.assertIn("c.orders_total", list_source)
        self.assertLess(list_source.index("{ title: '商机'"), list_source.index("{ title: '订单'"))
        self.assertLess(list_source.index("{ title: '订单'"), list_source.index("{ title: '累计成交'"))
        self.assertIn("leadTagSummaryHtml(c.tags)", list_source)

    def test_customer_detail_restores_customer_360_and_keeps_lead_tag_display(self):
        detail = self.customers[
            self.customers.index("function customer360OverviewHtml"):
            self.customers.index("function viewCustomerDetail")
        ]
        for marker in (
            "customer-360-facts",
            "累计订单额",
            "近 6 个月业务动态",
            "customer-360-journey",
            "最近一次跟进",
            "来源 / 意向",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, detail)
        self.assertIn("infoHtml: customer360OverviewHtml(c, records)", self.customers)
        self.assertNotIn("beforeTimelineHtml:", self.customers)
        self.assertIn("lead-detail-title-line", self.customers[self.customers.index("function viewCustomerDetail"):])

    def test_customer_timeline_is_progressive(self):
        detail = self.customers[self.customers.index("function viewCustomerDetail"):]
        self.assertIn("initialTimelineLimit: 6", detail)
        self.assertIn("timelineBatchSize: 6", detail)
        self.assertIn("btnLoadMoreTimeline", self.shared)
        self.assertIn("timelineLoaded += nextBatch.length", self.shared)
        self.assertIn("timelineRemaining", self.shared)
        self.assertIn("还没有跟进记录", self.shared)

    def test_customer_360_assets_are_cache_busted(self):
        self.assertIn("/crm/customer-360.css?v=20261105customer-ui3", self.index)
        self.assertIn("/crm/views/customers.js?v=20261105customer-ui3", self.index)
        self.assertIn("/crm/views/shared.js?v=20261105lead-tags6", self.index)
        self.assertIn("/crm/customer-360.css", self.sw)
        self.assertIn("crm-shell-v78", self.sw)

    def test_customer_360_is_responsive(self):
        self.assertIn("grid-template-columns: minmax(0, 1.08fr) minmax(340px, .92fr)", self.css)
        self.assertIn("grid-template-columns: repeat(6, minmax(26px, 1fr))", self.css)
        self.assertIn("@media (max-width: 980px)", self.css)
        self.assertIn("@media (max-width: 620px)", self.css)


if __name__ == "__main__":
    unittest.main()
