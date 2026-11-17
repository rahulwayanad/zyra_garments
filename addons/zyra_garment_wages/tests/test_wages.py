from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.zyra_garment_cutting.tests.common import CuttingCase


@tagged("post_install", "-at_install", "zyra")
class TestWages(CuttingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("zyra_garment_sewing.minute_rate", "2.0")
        cls.wline = cls.env["garment.line"].create({"name": "Wage Test Line", "code": "WTL",
                                                     "operator_count": 5, "working_minutes": 480})
        cls.card = cls.env["garment.rate.card"].create({
            "name": "Test Card", "minute_value": 1.0, "hours_per_day": 8, "min_daily_wage": 400,
            "overtime_multiplier": 2.0, "incentive_threshold": 80, "incentive_percent": 10})
        cls.WL = cls.env["garment.wage.sheet.line"]
        cls.expense = cls.env["account.account"].create({"name": "Wages Exp", "code": "WEXP1",
                                                         "account_type": "expense"})
        cls.payable = cls.env["account.account"].create({"name": "Wages Pay", "code": "WPAY1",
                                                         "account_type": "liability_current"})
        cls.journal = cls.env["account.journal"].create({"name": "Wages", "code": "WGJ", "type": "general"})

    def _scanned_bundle(self):
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
        return bundle

    def _sheet(self):
        today = date.today()
        return self.env["garment.wage.sheet"].create({
            "line_id": self.wline.id, "rate_card_id": self.card.id, "date_from": today, "date_to": today,
            "journal_id": self.journal.id, "expense_account_id": self.expense.id,
            "payable_account_id": self.payable.id})

    def test_topup_to_minimum(self):
        """Rule: top-up = days × minimum − piece earnings, never negative."""
        f = self.WL._garment_wage_figures(self.card, minutes=300, days=1)
        self.assertAlmostEqual(f["piece_earnings"], 300)
        self.assertAlmostEqual(f["topup"], 100)
        self.assertAlmostEqual(f["net_payable"], 400)
        f = self.WL._garment_wage_figures(self.card, minutes=450, days=1)
        self.assertEqual(f["topup"], 0)

    def test_overtime(self):
        """Rule: OT pay = OT hours × (minimum/day ÷ hours/day) × multiplier."""
        f = self.WL._garment_wage_figures(self.card, minutes=0, days=0, overtime_hours=2)
        self.assertAlmostEqual(f["overtime_pay"], 2 * 50 * 2)

    def test_incentive_threshold(self):
        """Rule: incentive only when efficiency is strictly above the card threshold."""
        at = self.WL._garment_wage_figures(self.card, minutes=384, days=1)  # exactly 80 %
        self.assertAlmostEqual(at["efficiency"], 80)
        self.assertEqual(at["incentive"], 0)
        above = self.WL._garment_wage_figures(self.card, minutes=432, days=1)  # 90 %
        self.assertAlmostEqual(above["incentive"], 43.2)

    def test_sheet_from_scans_post_and_no_double_count(self):
        self._scanned_bundle()
        sheet = self._sheet()
        sheet.action_compute()
        self.assertEqual(len(sheet.line_ids), 1)
        wl = sheet.line_ids
        scans = self.env["garment.scan"].search([("line_id", "=", self.wline.id)])
        self.assertTrue(scans)
        self.assertEqual(wl.scan_ids, scans)
        self.assertAlmostEqual(wl.minutes_earned, sum(scans.mapped("minutes_earned")))
        self.assertEqual(wl.days, 1)
        self.assertAlmostEqual(wl.net_payable, max(wl.minutes_earned, 400) + wl.incentive)
        # recompute keeps the same scans; a second sheet finds none
        sheet.action_compute()
        self.assertEqual(sheet.line_ids.scan_ids, scans)
        other = self._sheet()
        other.action_compute()
        self.assertFalse(other.line_ids)
        with self.assertRaises(UserError):
            other.action_post()
        sheet.line_ids.overtime_hours = 1
        sheet.action_post()
        move = sheet.move_id
        self.assertEqual(move.state, "posted")
        self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit")))
        self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sheet.total_net)
        with self.assertRaises(UserError):
            sheet.unlink()
