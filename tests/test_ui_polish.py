"""Regression checks for the presentation-only UI polish layer."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


class UiPolishTest(unittest.TestCase):
    def setUp(self):
        self.index = (STATIC / "index.html").read_text(encoding="utf-8")
        self.css = (STATIC / "ui-polish.css").read_text(encoding="utf-8")
        self.service_worker = (STATIC / "sw.js").read_text(encoding="utf-8")

    def test_polish_layer_loads_after_existing_styles(self):
        app_css = self.index.index("/crm/app.css")
        dashboard_css = self.index.index("/crm/dashboard-stats.css")
        order_css = self.index.index("/crm/order-detail.css")
        polish_css = self.index.index("/crm/ui-polish.css")

        self.assertLess(app_css, polish_css)
        self.assertLess(dashboard_css, polish_css)
        self.assertLess(order_css, polish_css)
        self.assertIn("/crm/ui-polish.css", self.service_worker)

    def test_polish_covers_shared_and_mobile_ui(self):
        for marker in (
            "--ui-accent:",
            ".topbar {",
            ".card {",
            ".btn-primary {",
            ".tab-btn.active {",
            "table.data-table th {",
            ".login-card {",
            ".modal-content {",
            ".ds-kpi {",
            ".order-command-card {",
            "a:focus-visible",
            "@media (max-width: 720px)",
            "@media (prefers-reduced-motion: reduce)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.css)

    def test_polish_layer_does_not_add_script(self):
        self.assertNotIn("<script", self.css.lower())
        self.assertNotIn("javascript:", self.css.lower())


if __name__ == "__main__":
    unittest.main()
