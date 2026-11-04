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
        self.index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.sw = (STATIC / "sw.js").read_text(encoding="utf-8")

    def test_customer_detail_has_full_profile_and_live_charts(self):
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

    def test_customer_timeline_is_progressive(self):
        detail = self.customers[self.customers.index("function viewCustomerDetail"):]
        self.assertIn("initialTimelineLimit: 6", detail)
        self.assertIn("timelineBatchSize: 6", detail)
        self.assertIn("btnLoadMoreTimeline", self.shared)
        self.assertIn("timelineLoaded += nextBatch.length", self.shared)
        self.assertIn("timelineRemaining", self.shared)
        self.assertIn("还没有跟进记录", self.shared)

    def test_customer_360_assets_are_cache_busted(self):
        self.assertIn("/crm/customer-360.css?v=20261104customer1", self.index)
        self.assertIn("/crm/views/customers.js?v=20261104customer1", self.index)
        self.assertIn("/crm/views/shared.js?v=20261104customer1", self.index)
        self.assertIn("/crm/customer-360.css", self.sw)
        self.assertIn("crm-shell-v67", self.sw)

    def test_customer_360_is_responsive_and_reduced_motion_safe(self):
        self.assertIn("grid-template-columns: minmax(0, 1.08fr) minmax(340px, .92fr)", self.css)
        self.assertIn("@media (max-width: 980px)", self.css)
        self.assertIn("@media (max-width: 620px)", self.css)


if __name__ == "__main__":
    unittest.main()
