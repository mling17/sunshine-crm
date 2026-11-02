"""Static checks for order editing before shipment."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OrderEditUiTest(unittest.TestCase):
    def test_order_detail_exposes_edit_button_and_shipped_lock(self):
        source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.assertIn("var ORDER_EDIT_LOCKED_STATUSES = { shipped: true, completed: true };", source)
        self.assertIn("function canEditOrder(order)", source)
        self.assertIn("id=\"btnEditOrder\">修改订单</button>", source)
        self.assertIn('title="订单已发货，不能再修改">修改订单</button>', source)

    def test_edit_modal_updates_delivery_tracking_and_note(self):
        source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        edit = source[
            source.index("function openOrderEditModal"):
            source.index("function showCustomerConfirmModal")
        ]
        for marker in (
            "createOrderModal('修改订单')",
            "receiver_name",
            "receiver_phone",
            "receiver_address",
            "tracking_number",
            "name=\"note\"",
            "api('/orders/' + order.id, { method: 'PUT', body: payload })",
        ):
            self.assertIn(marker, edit)


if __name__ == "__main__":
    unittest.main()
