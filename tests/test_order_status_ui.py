"""订单状态进度条的静态 UI 校验。"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OrderStatusUiTest(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.app = (ROOT / "static/app.js").read_text(encoding="utf-8")
        self.css = (ROOT / "static/app.css").read_text(encoding="utf-8")

    def _rule(self, selector: str) -> str:
        match = re.search(
            rf"(?ms)^{re.escape(selector)}\s*\{{(.*?)^\}}",
            self.css,
        )
        self.assertIsNotNone(match, f"missing CSS rule: {selector}")
        return match.group(1)

    def test_progress_uses_done_current_and_pending_colors(self):
        progress = self.source[
            self.source.index("var progressHtml"):
            self.source.index("/* 关联商机")
        ]
        self.assertIn(
            "i === stepIdx ? ' active' : (i < stepIdx ? ' done' : '')",
            progress,
        )

        pending = self._rule(".progress-bar .step")
        done = self._rule(".progress-bar .step.done")
        active = self._rule(".progress-bar .step.active")
        self.assertIn("background: #f3f4f6", pending)
        self.assertIn("color: #8a94a3", pending)
        self.assertIn("background: #e9f8f1", done)
        self.assertIn("color: #087955", done)
        self.assertIn("background: #eaf2ff", active)
        self.assertIn("color: #1c5fbb", active)
        self.assertNotIn("data-status=\"pending_", self.css)

    def test_progress_bar_has_no_dot_overlay_or_duplicate_layout(self):
        self.assertNotIn(".progress-bar .step::after", self.css)
        self.assertNotIn(".progress-bar::before", self.css)
        self.assertEqual(
            len(re.findall(r"(?m)^\.progress-bar\s*\{", self.css)),
            1,
        )
        active = self._rule(".progress-bar .step.active")
        self.assertIn("box-shadow:", active)
        self.assertIn("font-weight: 700", active)

    def test_confirm_shipping_completes_order_without_shipped_status(self):
        self.assertIn("ready_to_ship: ['completed', '确认发货']", self.source)
        self.assertIn(
            "transitionOrder(order, 'completed', extra, '确认发货')",
            self.source,
        )
        self.assertNotIn("['shipped', '已发货']", self.app)
        self.assertNotIn("'ready_to_ship': 'shipped'", self.app)


if __name__ == "__main__":
    unittest.main()
