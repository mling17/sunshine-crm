"""Static checks for order editing and logistics contact selection."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OrderEditUiTest(unittest.TestCase):
    def test_completed_order_hides_edit_button(self):
        source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        self.assertIn("function canEditOrder(order)", source)
        self.assertIn("if (order.status !== 'completed') {", source)
        self.assertIn("id=\"btnEditOrder\">修改订单</button>", source)

    def test_edit_modal_updates_all_order_owned_fields(self):
        source = (ROOT / "static/views/orders.js").read_text(encoding="utf-8")
        edit = source[
            source.index("function openOrderEditModal"):
            source.index("function openAftersaleModal")
        ]
        for marker in (
            "createOrderModal('修改订单')",
            "name=\"order_name\"",
            "name=\"order_no\"",
            "订单编号（不可修改）",
            "name=\"logistics_mode\"",
            "name=\"carrier_id\"",
            "name=\"carrier_contact_id\"",
            "name=\"logistics_fee\"",
            "receiver_name",
            "receiver_phone",
            "receiver_address",
            "name=\"address_id\"",
            "历史收件人及地址",
            "api('/customers/' + order.customer_id + '/addresses')",
            "tracking_number",
            "name=\"note\"",
            "api('/orders/' + order.id, { method: 'PUT', body: payload })",
        ):
            self.assertIn(marker, edit)
        self.assertIn("产品明细、报价金额、优惠和商机来源保持只读", edit)

    def test_create_order_requires_carrier_contact(self):
        source = (ROOT / "static/views/deals.js").read_text(encoding="utf-8")
        create = source[
            source.index("function openDealOrderModal"):
        ]
        self.assertIn('name="order_name"', create)
        self.assertIn("历史收件人及地址", create)
        self.assertIn("api('/customers/' + deal.customer_id + '/addresses')", create)
        self.assertIn("payload.address_id = Number(addressEl.value)", create)
        self.assertIn("item.product_name_snapshot ||", create)
        self.assertNotIn("dealItemName(item)", create)
        self.assertIn('name="carrier_contact_id"', create)
        self.assertIn("payload.carrier_contact_id = Number(carrierContactEl.value)", create)
        self.assertIn("请选择物流公司的联络人", create)


if __name__ == "__main__":
    unittest.main()
