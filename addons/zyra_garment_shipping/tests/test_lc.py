from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import ShippingCase


@tagged("post_install", "-at_install", "zyra")
class TestLc(ShippingCase):

    def _lc(self, **vals):
        return self.env["garment.lc"].create(dict({
            "name": "LCT-1", "buyer_id": self.buyer.id, "amount": 40000.0, "tolerance_pct": 5.0,
            "latest_shipment_date": self.today + timedelta(days=11),
            "expiry_date": self.today + timedelta(days=30),
        }, **vals))

    def test_lc_balance_is_amount_minus_drawings(self):
        lc = self._lc()
        lc.action_open()
        self.env["garment.lc.drawing"].create({"lc_id": lc.id, "amount": 4417.80})
        self.env["garment.lc.drawing"].create({"lc_id": lc.id, "amount": 582.20})
        self.assertAlmostEqual(lc.drawn, 5000.0)
        self.assertAlmostEqual(lc.balance, 35000.0)

    def test_drawings_cannot_exceed_amount_plus_tolerance(self):
        lc = self._lc()
        self.env["garment.lc.drawing"].create({"lc_id": lc.id, "amount": 42000.0})  # exactly +5 %
        with self.assertRaises(ValidationError):
            self.env["garment.lc.drawing"].create({"lc_id": lc.id, "amount": 0.01})

    def test_days_left_counts_to_expiry_and_expired_lc_shows_expired(self):
        lc = self._lc()
        lc.action_open()
        self.assertEqual(lc.days_left, 30)
        self.assertEqual(lc.display_state, "open")
        lc.write({"latest_shipment_date": self.today - timedelta(days=20),
                  "expiry_date": self.today - timedelta(days=1)})
        self.assertTrue(lc.is_expired)
        self.assertEqual(lc.days_left, 0)
        self.assertEqual(lc.display_state, "expired")
        self.assertIn(lc, self.env["garment.lc"].search([("is_expired", "=", True)]))

    def test_expiry_before_latest_shipment_date_posts_a_warning(self):
        lc = self._lc(expiry_date=self.today + timedelta(days=6))
        self.assertTrue(lc.expiry_before_shipment)
        self.assertIn("Ask the buyer for an amendment", " ".join(lc.message_ids.mapped("body")))

    def test_amendment_changes_terms_and_is_logged(self):
        lc = self._lc(expiry_date=self.today + timedelta(days=6))
        lc.action_open()
        wiz = self.env["garment.lc.amend.wizard"].with_context(default_lc_id=lc.id).create({
            "reason": "Expiry extended at the buyer's request"})
        wiz.expiry_date = self.today + timedelta(days=40)
        wiz.action_amend()
        self.assertEqual(lc.expiry_date, self.today + timedelta(days=40))
        self.assertEqual(lc.amendment_count, 1)
        self.assertFalse(lc.expiry_before_shipment)
        self.assertIn("Amendment 1", " ".join(lc.message_ids.mapped("body")))

    def test_tolerance_label(self):
        self.assertEqual(self._lc().tolerance_label, "± 5%")
