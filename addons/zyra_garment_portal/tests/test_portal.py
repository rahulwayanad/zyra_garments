import re
from datetime import timedelta

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.zyra_garment_merch.tests.common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestGarmentPortal(HttpCase, MerchCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.other_buyer = env["res.partner"].create({"name": "Portal Other Buyer", "is_garment_buyer": True})
        cls.contact = env["res.partner"].create({"name": "Portal Buyer Contact", "parent_id": cls.buyer.id})
        cls.buyer_user = new_test_user(env, "zp_buyer", groups="base.group_portal", partner_id=cls.contact.id)
        cls.other_contact = env["res.partner"].create({"name": "Other Contact", "parent_id": cls.other_buyer.id})
        cls.other_user = new_test_user(env, "zp_other", groups="base.group_portal",
                                       partner_id=cls.other_contact.id)
        cls.order = cls.make_order(cls, ex_days=-2)  # late
        cls.order.name = "PO/ZP/0001"
        cls.other_style = env["garment.style"].create({
            "name": "Other Buyer Style", "code": "ZP-OTHER", "buyer_id": cls.other_buyer.id,
            "size_range_id": cls.size_range.id})
        cls.other_order = env["garment.order"].create({
            "style_id": cls.style.id, "buyer_id": cls.other_buyer.id,
            "ex_factory_date": cls.today + timedelta(days=20), "date_order": cls.today})
        for line in cls.other_order.line_ids:
            line.qty_ordered = 5
        cls.other_order.action_confirm()
        cls.other_order.name = "PO/ZP/9999"
        cls.vendor = env["res.partner"].create({"name": "Portal Test Embroidery", "is_jobwork_vendor": True})
        cls.vendor_contact = env["res.partner"].create({"name": "Vendor Contact", "parent_id": cls.vendor.id})
        cls.vendor_user = new_test_user(env, "zp_vendor", groups="base.group_portal",
                                        partner_id=cls.vendor_contact.id)
        cls.job = env["garment.jobwork.order"].create({
            "process": "embroidery", "vendor_id": cls.vendor.id, "qty_sent": 620, "rate": 6.0,
            "note": "crest", "production_order_id": cls.order.id,
            "date_issue": cls.today - timedelta(days=10), "date_expected": cls.today - timedelta(days=3)})
        cls.job.action_send()

    def _csrf(self):
        page = self.url_open("/my/garment/approvals").text
        return re.search(r'csrf_token: "([^"]+)"', page).group(1)

    def test_buyer_cannot_read_another_buyers_order(self):
        """Record rule: a portal buyer only sees orders of their own company."""
        Order = self.env["garment.order"].with_user(self.buyer_user)
        self.assertIn(self.order, Order.search([]))
        self.assertNotIn(self.other_order, Order.search([]))
        with self.assertRaises(AccessError):
            self.other_order.with_user(self.buyer_user).read(["name"])
        self.assertNotIn(self.other_style, self.env["garment.style"].with_user(self.buyer_user).search([]))

    def test_buyer_cannot_open_another_buyers_order_page(self):
        """Order page of another buyer answers 404 and never shows its number."""
        self.authenticate("zp_buyer", "zp_buyer")
        resp = self.url_open("/my/garment/orders/%d" % self.other_order.id)
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn("PO/ZP/9999", resp.text)

    def test_buyer_pages_render(self):
        """Home (122), orders (123), order (124), styles and approvals render with the buyer's own data."""
        self.authenticate("zp_buyer", "zp_buyer")
        home = self.url_open("/my/garment")
        self.assertEqual(home.status_code, 200)
        self.assertIn("PO/ZP/0001", home.text)
        self.assertIn("buyer portal", home.text)
        self.assertNotIn("PO/ZP/9999", home.text)
        orders = self.url_open("/my/garment/orders")
        self.assertEqual(orders.status_code, 200)
        self.assertIn("Late", orders.text)
        detail = self.url_open("/my/garment/orders/%d" % self.order.id)
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Progress by colourway", detail.text)
        self.assertIn("Merch Red", detail.text)
        for url in ("/my/garment/styles", "/my/garment/approvals"):
            self.assertEqual(self.url_open(url).status_code, 200, url)

    def test_vendor_page_lists_own_jobs_only(self):
        """Screen 125: the vendor sees the jobs it holds, pending pieces and Overdue; buyers see none."""
        self.authenticate("zp_vendor", "zp_vendor")
        self.assertTrue(self.url_open("/my/garment").url.endswith("/my/garment/jobwork"))
        page = self.url_open("/my/garment/jobwork")
        self.assertEqual(page.status_code, 200)
        self.assertIn(self.job.name, page.text)
        self.assertIn("620", page.text)
        self.assertIn("Overdue", page.text)
        self.assertFalse(self.env["garment.jobwork.order"].with_user(self.buyer_user).search([]))
        with self.assertRaises(AccessError):
            self.order.with_user(self.vendor_user).read(["name"])

    def test_buyer_approves_sample_and_lab_dip(self):
        """Buyers approve samples and lab dips from the portal (only their own)."""
        sample = self.env["garment.sample"].create({
            "style_id": self.style.id, "buyer_id": self.buyer.id, "sample_type": "pp"})
        sample.action_send_to_buyer()
        card = self.env["garment.approval"].create({
            "kind": "lab_dip", "style_id": self.style.id, "buyer_id": self.buyer.id, "colour_id": self.red.id,
            "option_ids": [(0, 0, {"name": "A"}), (0, 0, {"name": "B"})]})
        card.action_send()
        self.authenticate("zp_buyer", "zp_buyer")
        page = self.url_open("/my/garment/approvals")
        self.assertIn(sample.name, page.text)
        self.assertIn(card.name, page.text)
        self.url_open("/my/garment/sample/%d/decide" % sample.id,
                      data={"decision": "approve", "comment": "Good fit", "csrf_token": self._csrf()})
        self.assertEqual(sample.state, "approved")
        option_b = card.option_ids.filtered(lambda o: o.name == "B")
        self.url_open("/my/garment/approval/%d/decide" % card.id,
                      data={"decision": "approve", "option_id": option_b.id, "csrf_token": self._csrf()})
        self.assertEqual(card.state, "approved")
        self.assertEqual(card.chosen_option_id, option_b)

    def test_other_buyer_cannot_decide_my_sample(self):
        """A buyer posting a decision on another buyer's sample gets 404 and nothing changes."""
        sample = self.env["garment.sample"].create({
            "style_id": self.style.id, "buyer_id": self.buyer.id, "sample_type": "fit"})
        sample.action_send_to_buyer()
        self.authenticate("zp_other", "zp_other")
        resp = self.url_open("/my/garment/sample/%d/decide" % sample.id,
                             data={"decision": "approve", "csrf_token": self._csrf()})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(sample.state, "with_buyer")
