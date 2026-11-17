from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.zyra_garment_cutting.tests.common import CuttingCase


@tagged("post_install", "-at_install", "zyra")
class TestSewing(CuttingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("zyra_garment_sewing.minute_rate", "2.0")
        cls.sew_line = cls.env["garment.line"].create({"name": "Sew Test Line", "code": "STL",
                                                        "operator_count": 10, "working_minutes": 480})
        cls.operator2 = cls.env["hr.employee"].create({"name": "Sew Test Operator Two"})

    def _bundle(self):
        plan = self.make_plan(bundle_size=40)
        plan.action_propose()
        plan.action_approve()
        lay = plan.lay_ids.sorted("lay_no")[0]
        self.cut_lay(lay)
        lay.action_create_bundles()
        bundle = lay.bundle_ids.sorted("id")[0]
        bundle.action_issue(self.sew_line.workcenter_id)
        return bundle

    def _payloads(self, bundle):
        return [c.payload for c in bundle.coupon_ids.sorted("sequence")]

    # --- line balancing maths -------------------------------------------------
    def test_balancing_rule_pitch_target_bottleneck_and_loss(self):
        """Rule: pitch = total SAM ÷ operators; target/h = operators × 60 ÷ SAM; balance loss from bottleneck."""
        res = self.env["garment.line.balancing"]._garment_balance([0.5, 1.0, 1.5], 6)
        self.assertAlmostEqual(res["pitch"], 0.5)
        self.assertEqual(res["target"], 120)
        self.assertEqual(res["alloc"], [1, 2, 3])
        self.assertEqual(res["balanced"], 120)
        self.assertEqual(res["loss"], 0.0)
        res = self.env["garment.line.balancing"]._garment_balance([0.6, 1.0, 1.4], 5)
        self.assertLessEqual(res["allocated"], 5)
        neck_cycle = max(res["cycles"])
        self.assertEqual(res["balanced"], int(60 / neck_cycle))
        self.assertEqual(res["loss"], round((1 - 3.0 / (res["allocated"] * neck_cycle)) * 100, 1))
        self.assertGreater(res["loss"], 0)

    def test_balancing_wizard_on_bulletin(self):
        bulletin = self.env["garment.bulletin"].create({"style_id": self.style.id})
        bulletin.action_load_from_techpack()
        self.assertEqual(bulletin.operation_count, 2)
        self.assertAlmostEqual(bulletin.total_sam, 1.2)
        self.assertEqual(bulletin.line_ids.sorted("sequence")[0].target_per_hour, 150)  # 60 / 0.4
        wiz = self.env["garment.line.balancing"].create({"bulletin_id": bulletin.id, "operators": 2,
                                                         "line_id": self.sew_line.id})
        self.assertEqual(wiz.target_output, 100)  # 2 × 60 ÷ 1.2
        self.assertEqual(wiz.balanced_output, 75)  # 60 ÷ 0.8
        self.assertEqual(wiz.bottleneck, "Attach sleeves")
        self.assertEqual(len(wiz.station_ids), 2)
        wiz.action_apply()
        self.assertEqual(self.sew_line.current_bulletin_id, bulletin)

    # --- scans ------------------------------------------------------------------
    def test_scan_minutes_and_earnings_rule(self):
        """Rule: minutes earned = pieces × SAM; earnings = minutes × minute rate."""
        bundle = self._bundle()
        scan = self.env["garment.scan"]._garment_scan(self._payloads(bundle)[0], self.operator)
        self.assertEqual(scan.pieces, bundle.pieces)
        self.assertAlmostEqual(scan.minutes_earned, bundle.pieces * 0.4)
        self.assertAlmostEqual(scan.earnings, bundle.pieces * 0.4 * 2.0)
        self.assertEqual(scan.line_id, self.sew_line)
        self.assertEqual(bundle.stage, "in_sewing")

    def test_duplicate_coupon_refused(self):
        bundle = self._bundle()
        payload = self._payloads(bundle)[0]
        self.env["garment.scan"]._garment_scan(payload, self.operator)
        with self.assertRaises(UserError):
            self.env["garment.scan"]._garment_scan(payload, self.operator2)
        self.assertEqual(self.env["garment.scan"].search_count([("bundle_id", "=", bundle.id)]), 1)

    def test_last_operation_completes_bundle_and_posts_sewn(self):
        bundle = self._bundle()
        sewn_before = self.order.qty_sewn
        first, last = self._payloads(bundle)
        self.assertFalse(self.env["garment.scan"]._garment_scan(first, self.operator).is_last_operation)
        scan = self.env["garment.scan"]._garment_scan(last, self.operator2)
        self.assertTrue(scan.is_last_operation)
        self.assertEqual(bundle.stage, "sewn")
        self.assertEqual(self.order.qty_sewn, sewn_before + bundle.pieces)

    def test_offline_batch_replay_is_idempotent(self):
        bundle = self._bundle()
        first, last = self._payloads(bundle)
        items = [
            {"uuid": "dev1-1", "payload": first, "employee_id": self.operator.id},
            {"uuid": "dev1-2", "payload": last, "employee_id": self.operator2.id},
            {"uuid": "dev1-3", "payload": first, "employee_id": self.operator2.id},  # same coupon again
            {"uuid": "dev1-4", "payload": "ZG1|1|1|BADBAD", "employee_id": self.operator.id},
        ]
        res = self.env["garment.scan"].garment_sync_batch(items)
        self.assertEqual([r["status"] for r in res], ["ok", "ok", "error", "error"])
        sewn = self.order.qty_sewn
        again = self.env["garment.scan"].garment_sync_batch(items[:2])
        self.assertEqual([r["status"] for r in again], ["duplicate", "duplicate"])
        self.assertEqual(self.env["garment.scan"].search_count([("bundle_id", "=", bundle.id)]), 2)
        self.assertEqual(self.order.qty_sewn, sewn)

    def test_daily_summary_efficiency_rule(self):
        """Rule: efficiency = earned minutes ÷ (operators × minutes per day) × 100."""
        bundle = self._bundle()
        for payload in self._payloads(bundle):
            self.env["garment.scan"]._garment_scan(payload, self.operator)
        summary = self.sew_line._garment_daily_summary()
        earned = bundle.pieces * 1.2
        self.assertAlmostEqual(summary["earned_minutes"], round(earned, 2))
        self.assertEqual(summary["available_minutes"], 4800)
        self.assertAlmostEqual(summary["efficiency"], round(earned / 4800 * 100, 1))
        self.assertAlmostEqual(summary["lost_minutes"], round(4800 - earned, 2))
        self.assertEqual(summary["pieces"], bundle.pieces)
        board = self.sew_line._garment_hourly_board(first_hour=0, hours=24)
        self.assertEqual(sum(h["output"] for h in board["hours"]), bundle.pieces)
        self.assertEqual(board["top_operator"], self.operator.name)

    def test_scan_without_badge_refused(self):
        bundle = self._bundle()
        with self.assertRaises(UserError):
            self.env["garment.scan"]._garment_scan(self._payloads(bundle)[0], self.env["hr.employee"])

    # --- scan station (screen 4) ------------------------------------------------
    def test_station_badge_finds_operator_by_barcode(self):
        self.operator.barcode = "ZS-BADGE-1"
        self.assertEqual(self.env["garment.scan"].station_badge("ZS-BADGE-1")["id"], self.operator.id)
        with self.assertRaises(UserError):
            self.env["garment.scan"].station_badge("NO-SUCH-BADGE")

    def test_station_stats_after_queued_scans(self):
        """Station sends its queue through garment_sync_batch, then reads the operator's figures."""
        bundle = self._bundle()
        first = self._payloads(bundle)[0]
        self.env["garment.scan"].garment_sync_batch(
            [{"uuid": "st-1", "payload": first, "employee_id": self.operator.id, "line_id": self.sew_line.id}])
        stats = self.env["garment.scan"].station_stats(self.operator.id, self.sew_line.id)
        self.assertEqual(stats["pieces"], bundle.pieces)
        self.assertAlmostEqual(stats["minutes"], round(bundle.pieces * 0.4, 1))
        self.assertAlmostEqual(stats["earnings"], round(bundle.pieces * 0.4 * 2.0, 2))
        self.assertEqual(stats["last"]["bundle"], bundle.name)

    # --- TV board (screen 56) ---------------------------------------------------
    def test_tv_board_data_from_hourly_board(self):
        bundle = self._bundle()
        for payload in self._payloads(bundle):
            self.env["garment.scan"]._garment_scan(payload, self.operator)
        data = self.sew_line.garment_tv_board()
        self.assertEqual(len(data["hours"]), 9)
        self.assertEqual(data["title"], self.sew_line.name)
        self.assertEqual(data["top_operator"], self.operator.name)
        self.assertGreaterEqual(data["max_bar"], 1)

    # --- daily line summary (screen 58) -------------------------------------------
    def test_line_day_figures_from_scans_and_close(self):
        bundle = self._bundle()
        at = fields.Datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        for payload in self._payloads(bundle):
            self.env["garment.scan"]._garment_scan(payload, self.operator, scanned_at=at)
        day = self.env["garment.line.day"].create({"line_id": self.sew_line.id})
        self.assertTrue(day.name.startswith("LD/"))
        self.assertEqual(day.pieces, bundle.pieces)
        self.assertEqual(day.available_minutes, 4800)
        self.assertAlmostEqual(day.earned_minutes, round(bundle.pieces * 1.2, 1), places=1)
        self.assertTrue(day.hour_ids)
        day.hour_ids[0].reason = "Late bundle issue"
        day.action_close()
        self.assertEqual(day.state, "closed")
        self.assertEqual(day.hour_ids[0].reason, "Late bundle issue")
        with self.assertRaises(UserError):
            day.action_refresh()
