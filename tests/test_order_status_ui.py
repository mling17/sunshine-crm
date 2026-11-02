"""订单状态进度条的静态 UI 校验。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_STATUSES = (
    "pending_confirmation",
    "pending_payment",
    "deposit_paid",
    "producing",
    "balance_paid",
    "ready_to_ship",
    "shipped",
    "completed",
)


class OrderStatusUiTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def test_progress_steps_expose_status_for_color_mapping(self):
        progress = self.source[
            self.source.index("var progressHtml"):
            self.source.index("/* 关联商机")
        ]
        self.assertIn('data-status="\' + p[0] + \'"', progress)
        for status in ORDER_STATUSES:
            self.assertIn(
                f'.progress-bar .step[data-status="{status}"]',
                self.css,
            )

    def test_progress_bar_has_no_dot_overlay_or_duplicate_layout(self):
        self.assertNotIn(".progress-bar .step::after", self.css)
        self.assertNotIn(".progress-bar::before", self.css)
        self.assertEqual(
            len(re.findall(r"(?m)^\.progress-bar\s*\{", self.css)),
            1,
        )
        self.assertIn(".progress-bar .step.active", self.css)
        self.assertIn("border-color: currentColor", self.css)


if __name__ == "__main__":
    unittest.main()
