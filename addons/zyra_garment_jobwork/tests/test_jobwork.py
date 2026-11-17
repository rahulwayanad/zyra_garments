from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestJobwork(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Test Stitch House", "is_jobwork_vendor": True})
        cls.today = fields.Date.today()

    def _order(self, qty=100, rate=10.0, allowance=2.0, **kw):
        vals = {"vendor_id": self.vendor.id, "process": "sewing", "qty_sent": qty, "rate": rate,
                "allowance_pct": allowance, "date_expected": self.today + timedelta(days=5)}
        vals.update(kw)
        return self.env["garment.jobwork.order"].create(vals)

    def test_sequence_and_send_moves_pieces_to_vendor_location(self):
        jw = self._order()
        self.assertTrue(jw.name.startswith("JW/"))
        jw.action_send()
        self.assertEqual(jw.state, "sent")
        loc = self.env.ref("zyra_garment_jobwork.stock_location_jobwork")
        move = jw.move_ids
        self.assertEqual(move.state, "done")
        self.assertEqual(move.location_dest_id, loc)
        self.assertEqual(move.quantity, 100)

    def test_send_needs_pieces_and_vendor(self):
        with self.assertRaises(UserError):
            self._order(qty=0).action_send()
        with self.assertRaises(UserError):
            self._order(vendor_id=False).action_send()

    def test_partial_receipts_move_state_and_pending(self):
        jw = self._order()
        jw.action_send()
        jw._garment_receive(40, 1)
        self.assertEqual(jw.state, "partly_received")
        self.assertEqual(jw.qty_pending, 59)
        jw._garment_receive(58, 1)
        self.assertEqual(jw.state, "received")
        self.assertEqual(jw.qty_pending, 0)
        self.assertEqual(jw.date_received, self.today)
        self.assertEqual(len(jw.move_ids), 3)

    def test_receipt_cannot_exceed_pending(self):
        jw = self._order(qty=10)
        jw.action_send()
        with self.assertRaises(ValidationError):
            jw._garment_receive(11)

    def test_process_loss_within_allowance(self):
        jw = self._order(qty=401, allowance=1.0)
        jw.action_send()
        jw._garment_receive(399, 2)
        self.assertAlmostEqual(jw.process_loss_pct, 2 / 401 * 100, places=2)
        self.assertFalse(jw.loss_over_allowance)

    def test_process_loss_over_allowance_counts_short(self):
        jw = self._order(qty=100, allowance=2.0)
        jw.action_send()
        jw._garment_receive(95, 1)
        jw.action_close_short()
        self.assertEqual(jw.qty_short, 4)
        self.assertEqual(jw.qty_rejected_short, 5)
        self.assertEqual(jw.state, "received")
        self.assertAlmostEqual(jw.process_loss_pct, 5.0)
        self.assertTrue(jw.loss_over_allowance)

    def test_billing_quantity_is_accepted_pieces_only(self):
        jw = self._order(qty=401, rate=14.5)
        jw.action_send()
        jw._garment_receive(399, 2)
        self.assertEqual(jw.qty_billable, 399)
        self.assertAlmostEqual(jw.jobwork_value, 5785.5)
        self.assertAlmostEqual(jw.bill_due, 5785.5)
        jw.action_bill()
        self.assertEqual(jw.state, "billed")
        self.assertEqual(jw.purchase_count, 1)
        po = jw.purchase_ids
        self.assertEqual(po.state, "purchase")
        self.assertEqual(po.partner_id, self.vendor)
        self.assertEqual(po.order_line.product_qty, 399)
        self.assertAlmostEqual(po.order_line.price_unit, 14.5)
        self.assertAlmostEqual(jw.bill_due, 0.0)

    def test_billing_refused_before_all_back(self):
        jw = self._order()
        jw.action_send()
        jw._garment_receive(50)
        with self.assertRaises(UserError):
            jw.action_bill()

    def test_overdue_when_expected_date_passed_and_pieces_out(self):
        jw = self._order(date_expected=self.today - timedelta(days=1))
        self.assertFalse(jw.is_overdue, "a draft is not overdue")
        jw.action_send()
        self.assertTrue(jw.is_overdue)
        Order = self.env["garment.jobwork.order"]
        self.assertIn(jw, Order.search([("is_overdue", "=", True)]))
        jw._garment_receive(100)
        self.assertFalse(jw.is_overdue, "received orders are never overdue")
        self.assertNotIn(jw, Order.search([("is_overdue", "=", True)]))

    def test_not_overdue_before_expected_date(self):
        jw = self._order()
        jw.action_send()
        self.assertFalse(jw.is_overdue)
        self.assertIn(jw, self.env["garment.jobwork.order"].search([("is_overdue", "=", False)]))

    def test_delivery_challan_renders(self):
        jw = self._order()
        jw.action_send()
        html, _fmt = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_jobwork.report_delivery_challan", jw.ids)
        self.assertIn(jw.name.encode(), html)
        self.assertIn(b"Delivery Challan", html)
