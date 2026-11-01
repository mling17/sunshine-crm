"""静态回归：转商机从跟进页发起，客户档案不可删除。"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FollowupDealEntryUiTest(unittest.TestCase):
    def setUp(self):
        self.leads = (ROOT / "static/views/leads.js").read_text(encoding="utf-8")
        self.customers = (ROOT / "static/views/customers.js").read_text(encoding="utf-8")

    @staticmethod
    def section(source: str, start: str, end: str) -> str:
        return source[source.index(start):source.index(end)]

    def test_lead_list_has_follow_but_no_deal_conversion(self):
        lead_list = self.section(self.leads, "function loadLeads", "function leadFormHtml")
        self.assertIn("op: 'follow'", lead_list)
        self.assertNotIn("op: 'toDeal'", lead_list)
        self.assertIn('id="leadToDealBtn"', self.leads)

    def test_customer_list_has_follow_but_no_deal_conversion(self):
        customer_list = self.section(
            self.customers, "function loadCustomers", "function openCustomerDealModal"
        )
        self.assertIn("op: 'follow'", customer_list)
        self.assertNotIn("op: 'toDeal'", customer_list)
        self.assertIn("$('#custToDeal', root)", self.customers)

    def test_customer_ui_has_no_delete_action(self):
        self.assertNotIn('id="deleteCustomer"', self.customers)
        self.assertNotIn("method: 'DELETE'", self.customers)


if __name__ == "__main__":
    unittest.main()
