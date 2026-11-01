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
        self.orders = (views / "orders.js").read_text(encoding="utf-8")

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

    def test_order_modal_separates_product_discount_and_freight(self):
        order_modal = self.deals[
            self.deals.index("function openDealOrderModal"):
        ]
        self.assertIn("<label>产品合计</label>", order_modal)
        self.assertIn("<label>整单优惠</label>", order_modal)
        self.assertIn("<label>优惠后产品应收</label>", order_modal)
        self.assertIn("<label>运费（我方收取）</label>", order_modal)
        self.assertIn("<label>订单应收</label>", order_modal)
        self.assertIn("<label>定金（第一笔）*</label>", order_modal)
        self.assertIn("优惠只减产品合计，运费单独计入订单应收", order_modal)
        self.assertIn("Math.round(receivable * 100) / 100", order_modal)
        self.assertNotIn("amount: amount,", order_modal)

    def test_deal_list_and_customer_deal_cards_do_not_prefill_deposit(self):
        deal_items = self.shared[
            self.shared.index("function dealItemHtml"):
            self.shared.index("function aftersaleTypeLabel")
        ]
        self.assertIn("报价金额", self.deals)
        self.assertNotIn("deal.deposit", deal_items)
        self.assertNotIn("deal.balance", deal_items)

    def test_deal_items_and_customer_confirmation_are_wired(self):
        self.assertIn("function openDealItemModal", self.deals)
        self.assertIn("function dealItemsCardHtml", self.deals)
        self.assertIn("/items", self.deals)
        self.assertIn("showCustomerConfirmModal", self.orders)
        self.assertIn("/confirm", self.orders)
        self.assertIn("客户通过微信查看下单表", self.orders)

    def test_quotation_upload_preview_and_followup_link_are_wired(self):
        for marker in (
            "function quoteCardsHtml",
            "function quoteFormPreviewHtml",
            "function openQuoteItemModal",
            "function openQuoteConfirmModal",
            'name="form_file"',
            "下载产品模板",
            "data-quote-confirm",
            "data-quote-order",
            "/quotes/items/",
        ):
            self.assertIn(marker, self.deals)
        self.assertIn("opts.followExtraHtml", self.shared)
        self.assertIn("payload.quote_id", self.shared)
        self.assertIn('name="quote_id"', self.deals)


if __name__ == "__main__":
    unittest.main()
