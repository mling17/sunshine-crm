"""Regression checks for quote-only deal amounts and shared entity follow-up pages."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DealQuoteAndFollowupUiTest(unittest.TestCase):
    def setUp(self):
        views = ROOT / "static" / "views"
        self.shared = (views / "shared.js").read_text(encoding="utf-8")
        self.leads = (views / "leads.js").read_text(encoding="utf-8")
        self.customers = (views / "customers.js").read_text(encoding="utf-8")
        self.deals = (views / "deals.js").read_text(encoding="utf-8")

    def test_leads_customers_and_deals_share_followup_timeline_adapter(self):
        self.assertIn("function followupRecordsFromApi(records)", self.shared)
        for source in (self.leads, self.customers, self.deals):
            self.assertIn("followupRecordsFromApi(", source)

    def test_customer_and_deal_details_use_shared_followup_page(self):
        customer_detail = self.customers[
            self.customers.index("function viewCustomerDetail"):
        ]
        deal_detail = self.deals[
            self.deals.index("function viewDealDetail"):
            self.deals.index("function openDealEdit")
        ]
        for source in (customer_detail, deal_detail):
            self.assertIn("renderEntityFollowPage(root", source)
            self.assertIn("fd.append('object_type'", source)
            self.assertIn("fd.append('method'", source)
            self.assertIn("fd.append('next_date'", source)
            self.assertIn("fd.append('files'", source)

    def test_deal_edit_only_contains_quote_amount(self):
        edit = self.deals[
            self.deals.index("function openDealEdit"):
            self.deals.index("function openDealLose")
        ]
        self.assertIn("<label>报价金额 *</label>", edit)
        self.assertNotIn('name="deposit"', edit)
        self.assertNotIn('name="balance"', edit)
        self.assertNotIn("deposit: numOrNull", edit)
        self.assertNotIn("balance: numOrNull", edit)

    def test_order_modal_shows_readonly_quote_and_calculates_balance(self):
        order_modal = self.deals[
            self.deals.index("function openDealOrderModal"):
        ]
        self.assertIn("报价金额（订单总额）", order_modal)
        self.assertIn('value="\' + amount0 + \'" readonly', order_modal)
        self.assertIn("<label>定金（第一笔）*</label>", order_modal)
        self.assertIn("定金 + 尾款 = 报价金额", order_modal)
        self.assertIn("Math.round((a - dep) * 100) / 100", order_modal)
        self.assertNotIn("amount: amount,", order_modal)

    def test_deal_list_and_customer_deal_cards_do_not_prefill_deposit(self):
        deal_items = self.shared[
            self.shared.index("function dealItemHtml"):
            self.shared.index("function aftersaleTypeLabel")
        ]
        self.assertIn("报价金额", self.deals)
        self.assertNotIn("deal.deposit", deal_items)
        self.assertNotIn("deal.balance", deal_items)


if __name__ == "__main__":
    unittest.main()
