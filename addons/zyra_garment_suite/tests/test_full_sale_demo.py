from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestFullSaleDemo(TransactionCase):
    """The demo sale (Coastline Outfitters, ST-0201) runs through every module; only checked when demo is loaded."""

    def setUp(self):
        super().setUp()
        self.order = self.env.ref("zyra_garment_suite.story_order", raise_if_not_found=False)
        if not self.order:
            self.skipTest("demo data not loaded")

    def ref(self, name):
        return self.env.ref("zyra_garment_suite." + name)

    def test_demo_order_is_shipped_in_full_and_completed(self):
        self.assertEqual(self.order.state, "closed")
        self.assertEqual(self.order.qty_shipped, self.order.qty_ordered)
        self.assertGreaterEqual(self.order.qty_cut, self.order.qty_ordered)
        self.assertTrue(self.order.final_passed)

    def test_demo_price_comes_from_the_cost_sheet_approved_below_the_floor(self):
        sheet = self.ref("story_cost_sheet")
        self.assertEqual(sheet.state, "approved")
        self.assertTrue(sheet.below_floor and sheet.floor_override_reason)
        self.assertEqual(self.ref("story_cost_sheet_v1").state, "superseded")
        self.assertAlmostEqual(self.order.price_unit, sheet.currency_id.round(sheet.fob_price))

    def test_demo_shipment_is_invoiced_paid_and_drawn_on_the_credit(self):
        shipment = self.ref("story_shipment")
        self.assertEqual(shipment.stage, "paid")
        invoice = self.ref("story_invoice")
        self.assertEqual(invoice.payment_state, "paid")
        self.assertAlmostEqual(shipment.lc_id.drawn, shipment.value)

    def test_demo_pnl_has_every_cost_source(self):
        pnl = self.ref("story_pnl")
        self.assertAlmostEqual(pnl.revenue, self.ref("story_invoice").amount_untaxed)
        for figure in ("actual_material", "actual_making", "actual_jobwork", "actual_other"):
            self.assertGreater(pnl[figure], 0, figure)

    def test_demo_wages_pay_every_scan_of_the_order_once(self):
        scans = self.env["garment.scan"].search([("order_id", "=", self.order.id)])
        self.assertTrue(scans)
        self.assertFalse(scans.filtered(lambda s: not s.wage_line_id))
        self.assertEqual(set(scans.wage_line_id.sheet_id.mapped("state")), {"posted"})
