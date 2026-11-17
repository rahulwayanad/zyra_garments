from datetime import date

from odoo.tests import tagged

from odoo.addons.zyra_garment_cutting.tests.common import CuttingCase


@tagged("post_install", "-at_install", "zyra")
class TestPnlFloorCosts(CuttingCase):
    """Floor sources: fabric cut on the order's lays (material) and wage sheets paying its scans (making)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.wline = env["garment.line"].create({"name": "PnL Line", "code": "PNL",
                                                "operator_count": 5, "working_minutes": 480})
        cls.card = env["garment.rate.card"].create({
            "name": "PnL Card", "minute_value": 1.0, "hours_per_day": 8, "min_daily_wage": 1,
            "overtime_multiplier": 2.0, "incentive_threshold": 999, "incentive_percent": 0,
            "topup_period": "weekly"})
        cls.card.action_activate()
        cls.expense = env["account.account"].create({"name": "PnL Wages Exp", "code": "PWEXP",
                                                     "account_type": "expense"})
        cls.payable = env["account.account"].create({"name": "PnL Wages Pay", "code": "PWPAY",
                                                     "account_type": "liability_current"})
        cls.journal = env["account.journal"].create({"name": "PnL Wages", "code": "PWGJ", "type": "general"})
        cls.operator.barcode = "PNLOP01"

    def test_fabric_cut_on_lays_is_material_and_paid_scans_are_making(self):
        plan = self.make_plan(bundle_size=40)
        plan.action_propose()
        plan.action_approve()
        lay = plan.lay_ids.sorted("lay_no")[0]
        self.cut_lay(lay)
        lay.action_create_bundles()
        bundle = lay.bundle_ids.sorted("id")[0]
        bundle.action_issue(self.wline.workcenter_id)
        for coupon in bundle.coupon_ids.sorted("sequence"):
            self.env["garment.scan"]._garment_scan(coupon.payload, self.operator)

        pnl = self.order._garment_pnl()
        moves = lay.move_ids.filtered(lambda m: m.state == "done")
        self.assertTrue(moves)
        expected = 0.0
        for move in moves:
            layers = move.stock_valuation_layer_ids
            expected += -sum(layers.mapped("value")) if layers else move.quantity * move.product_id.standard_price
        self.assertAlmostEqual(pnl.actual_material, expected, places=2)
        self.assertEqual(pnl.actual_making, 0.0, "unpaid scans are not a cost yet")

        sheet = self.env["garment.wage.sheet"].create({
            "line_id": self.wline.id, "rate_card_id": self.card.id, "date_from": date.today(),
            "date_to": date.today(), "journal_id": self.journal.id, "expense_account_id": self.expense.id,
            "payable_account_id": self.payable.id})
        sheet.action_compute()
        wl = sheet.line_ids
        self.assertEqual(len(wl), 1)
        pnl.action_refresh()
        # every scan on the wage line is for this order, so the whole net pay is its making cost
        self.assertAlmostEqual(pnl.actual_making, wl.net_payable, places=2)
        self.assertGreater(pnl.actual_making, 0)
