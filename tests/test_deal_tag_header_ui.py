"""商机标签与订单页头部标签的视觉一致性校验。"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DealTagHeaderUiTest(unittest.TestCase):
    def setUp(self):
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")
        self.index = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")

    def test_deal_tags_follow_customer_name_and_size_to_content(self):
        tags = self.css[
            self.css.index(".deal-tags {"):
            self.css.index(".deal-tag-system")
        ]
        self.assertIn("display: inline-flex", tags)
        self.assertIn("flex: 0 1 auto", tags)
        self.assertIn("height: 22px", tags)
        self.assertIn("border-radius: 10px", tags)
        self.assertNotIn("flex: 1 1 100%", tags)

    def test_asset_versions_are_updated_for_header_layout(self):
        self.assertIn('/crm/app.css?v=20261105lead-tags6', self.index)
        self.assertIn('/crm/views/leads.js?v=20261105lead-tags6', self.index)
        self.assertIn("const CACHE = 'crm-shell-v78';", self.sw)


if __name__ == "__main__":
    unittest.main()
