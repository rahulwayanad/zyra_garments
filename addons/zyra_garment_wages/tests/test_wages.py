from datetime import date, datetime, timedelta

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
            "overtime_multiplier": 2.0, "incentive_threshold": 80, "incentive_percent": 10,
            "topup_period": "weekly"})
        cls.card.action_activate()
        cls.WL = cls.env["garment.wage.sheet.line"]
        cls.expense = cls.env["account.account"].create({"name": "Wages Exp", "code": "WEXP1",
                                                         "account_type": "expense"})
        cls.payable = cls.env["account.account"].create({"name": "Wages Pay", "code": "WPAY1",
                                                         "account_type": "liability_current"})
        cls.journal = cls.env["account.journal"].create({"name": "Wages", "code": "WGJ", "type": "general"})
        cls.operator.barcode = "WTEST01"

    def _bundle(self):
        plan = self.make_plan(bundle_size=40)
        plan.action_propose()
        plan.action_approve()
        lay = plan.lay_ids.sorted("lay_no")[0]
        self.cut_lay(lay)
        lay.action_create_bundles()
        bundle = lay.bundle_ids.sorted("id")[0]
        bundle.action_issue(self.wline.workcenter_id)
        return bundle

    def _scanned_bundle(self, when=None):
        bundle = self._bundle()
        for coupon in bundle.coupon_ids.sorted("sequence"):
            self.env["garment.scan"]._garment_scan(coupon.payload, self.operator, scanned_at=when)
        return bundle

    def _sheet(self, day=None):
        day = day or date.today()
        return self.env["garment.wage.sheet"].create({
            "line_id": self.wline.id, "rate_card_id": self.card.id, "date_from": day, "date_to": day,
            "journal_id": self.journal.id, "expense_account_id": self.expense.id,
            "payable_account_id": self.payable.id})

    # --- pure rules ----------------------------------------------------------
    def test_weekly_topup_to_minimum(self):
        """Rule: weekly top-up = days × minimum − piece earnings, never negative."""
        f = self.WL._garment_wage_figures(self.card, [300])
        self.assertAlmostEqual(f["piece_earnings"], 300)
        self.assertAlmostEqual(f["topup"], 100)
        self.assertAlmostEqual(f["net_payable"], 400)
        self.assertEqual(self.WL._garment_wage_figures(self.card, [450])["topup"], 0)
        # a strong day covers a weak day when topped up weekly
        self.assertEqual(self.WL._garment_wage_figures(self.card, [500, 300])["topup"], 0)

    def test_daily_topup_counts_each_day(self):
        """Rule: daily top-up = Σ max(0, minimum − day earnings); a strong day does not cover a weak one."""
        self.card.write({"topup_period": "daily", "incentive_threshold": 100})
        f = self.WL._garment_wage_figures(self.card, [500, 300])
        self.assertAlmostEqual(f["topup"], 100)
        self.assertAlmostEqual(f["net_payable"], 900)

    def test_overtime(self):
        """Rule: OT pay = OT hours × (minimum/day ÷ hours/day) × overtime rate."""
        f = self.WL._garment_wage_figures(self.card, [], overtime_hours=2)
        self.assertAlmostEqual(f["overtime_pay"], 2 * 50 * 2)

    def test_incentive_threshold(self):
        """Rule: incentive only when efficiency is strictly above the card threshold (piece rate only)."""
        at = self.WL._garment_wage_figures(self.card, [384])  # exactly 80 %
        self.assertAlmostEqual(at["efficiency"], 80)
        self.assertEqual(at["incentive"], 0)
        above = self.WL._garment_wage_figures(self.card, [432])  # 90 %
        self.assertAlmostEqual(above["incentive"], 43.2)
        self.assertAlmostEqual(above["efficiency_ratio"], 0.9)

    def test_time_rate_gets_no_incentive_and_weekly_topup(self):
        """Rule: a time-rate operator is paid at least the minimum for the days attended, never an incentive."""
        self.card.topup_period = "daily"
        f = self.WL._garment_wage_figures(self.card, [500, 300], paid_by="time")
        self.assertEqual(f["incentive"], 0)
        self.assertEqual(f["topup"], 0)  # weekly: 800 earned ≥ 2 × 400
        self.assertAlmostEqual(f["net_payable"], 800)

    # --- rate card -----------------------------------------------------------
    def test_rate_card_hourly_and_apply_to_bulletins(self):
        """Rule: hourly at 100 % = minute value × 60; piece rate = SAM × minute value, manual rates kept."""
        self.assertTrue(self.card.code.startswith("RC/"))
        self.assertAlmostEqual(self.card.hourly_full, 60)
        bulletin = self.env["garment.bulletin"].create({"style_id": self.style.id})
        bulletin.action_load_from_techpack()
        manual = bulletin.line_ids.sorted("sequence")[0]
        manual.write({"manual_rate": True, "piece_rate": 9.0})
        other = bulletin.line_ids - manual
        draft = self.env["garment.rate.card"].create({"name": "Draft", "minute_value": 2, "min_daily_wage": 1})
        draft.bulletin_ids = bulletin
        with self.assertRaises(UserError):
            draft.action_apply_to_bulletins()
        self.card.bulletin_ids = bulletin
        self.assertEqual(self.card.bulletin_count, 1)
        self.card.action_apply_to_bulletins()
        self.assertEqual(manual.piece_rate, 9.0)
        for line in other:
            self.assertAlmostEqual(line.piece_rate, round(line.sam * 1.0, 4))
        self.assertEqual(bulletin.rate_card, "Test Card")
        self.assertAlmostEqual(bulletin.garment_rate_per_minute, bulletin.total_piece_rate / bulletin.total_sam,
                               places=2)

    # --- sheet flow ----------------------------------------------------------
    def test_sheet_from_scans_approve_post_and_no_double_count(self):
        """Rule: a scan is paid by one wage sheet only; post needs approval and makes one balanced entry."""
        self._scanned_bundle()
        sheet = self._sheet()
        week = date.today().isocalendar()[1]
        self.assertEqual(sheet.period_label, "Week %s · Wage Test Line" % week)
        sheet.action_compute()
        self.assertEqual(len(sheet.line_ids), 1)
        wl = sheet.line_ids
        scans = self.env["garment.scan"].search([("line_id", "=", self.wline.id)])
        self.assertTrue(scans)
        self.assertEqual(wl.scan_ids, scans)
        self.assertEqual(wl.badge, "WTEST01")
        self.assertEqual(wl.garment_line_id, self.wline)
        self.assertEqual(sheet.scan_count, len(scans))
        self.assertAlmostEqual(wl.minutes_earned, sum(scans.mapped("minutes_earned")))
        self.assertEqual(wl.days, 1)
        self.assertAlmostEqual(wl.net_payable, max(wl.minutes_earned, 400) + wl.incentive)
        self.assertEqual(sheet.below_minimum_count, 1 if wl.topup else 0)
        # recompute keeps the same scans and the typed overtime; a second sheet finds none
        wl.overtime_hours = 1
        sheet.action_compute()
        self.assertEqual(sheet.line_ids.scan_ids, scans)
        self.assertEqual(sheet.line_ids.overtime_hours, 1)
        other = self._sheet()
        other.action_compute()
        self.assertFalse(other.line_ids)
        with self.assertRaises(UserError):
            other.action_approve()
        with self.assertRaises(UserError):
            sheet.action_post()  # not approved yet
        sheet.action_approve()
        self.assertEqual(sheet.approved_by_id, self.env.user)
        with self.assertRaises(UserError):
            sheet.line_ids.overtime_hours = 3  # approved sheets are frozen
        sheet.action_post()
        move = sheet.move_id
        self.assertEqual(move.state, "posted")
        self.assertEqual(sheet.move_count, 1)
        self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sum(move.line_ids.mapped("credit")))
        self.assertAlmostEqual(sum(move.line_ids.mapped("debit")), sheet.total_net)
        self.assertIn(move.name, sheet.message_ids[0].body)
        with self.assertRaises(UserError):
            sheet.unlink()

    def test_cancel_posted_sheet_reverses_entry_and_frees_scans(self):
        """Rule: cancelling a posted sheet reverses its journal entry and lets another sheet pay the scans."""
        self._scanned_bundle()
        sheet = self._sheet()
        sheet.action_compute()
        paid = sheet.line_ids.scan_ids
        sheet.action_approve()
        sheet.action_post()
        move = sheet.move_id
        net = sheet.total_net
        sheet.action_cancel_posted()
        self.assertEqual(sheet.state, "cancel")
        reversal = self.env["account.move"].search([("reversed_entry_id", "=", move.id)])
        self.assertEqual(reversal.state, "posted")
        self.assertAlmostEqual(sum(reversal.line_ids.filtered(lambda l: l.account_id == self.expense).mapped("credit")),
                               net)
        again = self._sheet()
        again.action_compute()
        self.assertFalse(sheet.line_ids.scan_ids)
        self.assertEqual(again.line_ids.scan_ids, paid)

    def test_scans_outside_period_or_line_are_left_out(self):
        """Rule: a sheet pays only scans of its period and, when set, of its line."""
        yesterday = date.today() - timedelta(days=1)
        self._scanned_bundle(when=datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=6))
        sheet = self._sheet()  # today only
        sheet.action_compute()
        self.assertFalse(sheet.line_ids)
        sheet.action_reset()
        sheet.write({"date_from": yesterday, "line_id": self.line_id_other().id})
        sheet.action_compute()
        self.assertFalse(sheet.line_ids)
        sheet.action_reset()
        sheet.line_id = False
        self.assertTrue(sheet.period_label.endswith("whole floor"))
        sheet.action_compute()
        self.assertEqual(sheet.line_ids.filtered(lambda l: l.employee_id == self.operator).days, 1)

    def line_id_other(self):
        return self.env["garment.line"].create({"name": "Wage Other Line", "code": "WOL"})

    def test_wage_slip_work_done_and_render(self):
        """Rule: the slip groups work by order and operation; earnings = minutes × minute value."""
        self._scanned_bundle()
        sheet = self._sheet()
        sheet.action_compute()
        wl = sheet.line_ids
        rows = wl._garment_work_done()
        self.assertEqual(len(rows), len(wl.scan_ids.mapped("operation_line_id")))
        self.assertEqual(sum(r["pieces"] for r in rows), wl.pieces)
        self.assertAlmostEqual(sum(r["earnings"] for r in rows), wl.piece_earnings)
        self.assertTrue(sheet.action_print_slips())
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_wages.report_wage_slip", wl.ids)
        self.assertIn(b"Wage Slip", html)
        self.assertIn(self.operator.name.encode(), html)

    def test_wages_clerk_runs_the_week_without_accounting_rights(self):
        """Rule: the wages role computes, approves, posts and prints without HR or accounting rights."""
        clerk = self.env["res.users"].create({
            "name": "Wage Clerk", "login": "wage_clerk_test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("zyra_garment_base.group_garment_wages").id])]})
        self._scanned_bundle()
        sheet = self._sheet().with_user(clerk)
        sheet.action_compute()
        sheet.action_approve()
        sheet.action_post()
        self.assertEqual(sheet.state, "posted")
        self.assertEqual(sheet.sudo().move_id.state, "posted")
        self.assertTrue(sheet.line_ids.read(["badge", "employee_id", "net_payable", "efficiency_ratio"]))
