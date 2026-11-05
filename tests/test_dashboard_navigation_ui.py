"""工作台 KPI 数字卡的同页导航回归。"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class DashboardNavigationUiTest(unittest.TestCase):
    def setUp(self):
        self.dashboard = (STATIC / "views" / "dashboard.js").read_text(encoding="utf-8")
        self.index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.service_worker = (STATIC / "sw.js").read_text(encoding="utf-8")

    def test_today_and_overdue_cards_scroll_to_same_page_section(self):
        for label in ("今日待跟进", "已逾期"):
            block = re.search(
                r'label: "'
                + re.escape(label)
                + r'",(?P<body>.*?)\n\s*\}\)',
                self.dashboard,
                re.S,
            )
            self.assertIsNotNone(block, label)
            body = block.group("body")
            self.assertIn('href: "#/dashboard"', body)
            self.assertIn('scrollTarget: "today-followups"', body)
            self.assertNotIn('href: "#/followups"', body)

        self.assertIn('id="today-followups"', self.dashboard)
        self.assertIn('id="today-followups-title" tabindex="-1"', self.dashboard)

    def test_card_click_scrolls_and_moves_focus_without_route_change(self):
        self.assertIn('data-dashboard-scroll="', self.dashboard)
        self.assertIn("event.preventDefault();", self.dashboard)
        self.assertIn('window.matchMedia("(prefers-reduced-motion: reduce)")', self.dashboard)
        self.assertIn("window.scrollTo({", self.dashboard)
        self.assertIn("heading.focus({ preventScroll: true });", self.dashboard)

    def test_dashboard_script_and_cache_versions_are_refreshed(self):
        self.assertIn(
            "/crm/views/dashboard.js?v=20261105dashboard-scroll1",
            self.index,
        )
        self.assertIn("const CACHE = 'crm-shell-v79';", self.service_worker)


if __name__ == "__main__":
    unittest.main()
