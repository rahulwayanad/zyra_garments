from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MaterialsCase


@tagged("post_install", "-at_install", "zyra")
class TestFourPoint(MaterialsCase):

    def _inspection(self, roll, length=100.0, width=57.5):
        return self.env["garment.fabric.inspection"].create({
            "lot_id": roll.id, "inspected_length_yd": length, "cuttable_width_in": width})

    def _defects(self, insp, items):
        defect = self.env["garment.defect"].search([], limit=1)
        for yard, band in items:
            insp.tablet_add_defect(defect.id, band, yard)

    def test_points_per_100sqyd_is_points_x_3600_over_yards_x_width(self):
        insp = self.env["garment.fabric.inspection"]
        # Screen 44: 17 points on 103.89 yd of 57.5 in cuttable width → 10.2
        self.assertAlmostEqual(insp._formula_points_per_100sqyd(17, 103.89, 57.5), 10.245, places=3)
        self.assertAlmostEqual(insp._formula_points_per_100sqyd(40, 100, 36), 40.0)
        self.assertEqual(insp._formula_points_per_100sqyd(10, 0, 57.5), 0.0)

    def test_length_band_gives_1_to_4_points(self):
        roll = self.make_roll("RT-BAND")
        insp = self._inspection(roll)
        self._defects(insp, [(1, "1"), (2, "2"), (3, "3"), (4, "4")])
        self.assertEqual(insp.defect_line_ids.sorted("sequence").mapped("points"), [1, 2, 3, 4])
        self.assertEqual(insp.penalty_points, 10)
        self.assertAlmostEqual(insp.points_per_100sqyd, 10 * 3600 / (100 * 57.5), places=1)

    def test_no_more_than_4_points_per_linear_yard(self):
        roll = self.make_roll("RT-CAP")
        insp = self._inspection(roll)
        self._defects(insp, [(10.2, "4"), (10.7, "3"), (11.0, "2")])
        self.assertEqual(insp.penalty_points, 6, "yard 10 capped at 4, yard 11 adds 2")

    def test_accept_limit_comes_from_company_setting(self):
        self.company.garment_fabric_accept_points = 28.0
        insp = self._inspection(self.make_roll("RT-LIMIT"))
        self.assertEqual(insp.accept_limit, 28.0)

    def test_pass_under_the_limit_approves_the_roll(self):
        roll = self.make_roll("RT-PASS")
        insp = self._inspection(roll)
        self._defects(insp, [(5, "2"), (20, "1")])
        insp.action_done()
        self.assertEqual(insp.result, "pass")
        self.assertEqual(roll.roll_status, "approved")
        self.assertAlmostEqual(roll.points_per_100sqyd, insp.points_per_100sqyd, places=1)
        self.assertEqual(roll.roll_inspected_date, insp.date_inspected)

    def test_fail_over_the_limit_puts_the_roll_on_hold_with_the_reason(self):
        roll = self.make_roll("RT-FAIL")
        insp = self._inspection(roll, length=50.0, width=36.0)
        # 15 yards × 4 points = 60 points → 60 × 3600 / (50 × 36) = 120 > 40
        self._defects(insp, [(y, "4") for y in range(1, 16)])
        self.assertEqual(insp.result, "hold")
        insp.action_done()
        self.assertEqual(roll.roll_status, "hold")
        self.assertIn("120.0", roll.roll_hold_reason)
        self.assertIn("40.0", roll.roll_hold_reason)

    def test_inspector_can_hold_a_passing_roll_with_a_reason(self):
        roll = self.make_roll("RT-SHADE")
        insp = self._inspection(roll)
        self._defects(insp, [(3, "1")])
        insp.result_override = "hold"
        with self.assertRaises(UserError):
            insp.action_done()
        insp.reason = "Shade differs from the approved band"
        insp.action_done()
        self.assertEqual(insp.result, "hold")
        self.assertEqual(roll.roll_status, "hold")
        self.assertEqual(roll.roll_hold_reason, "Shade differs from the approved band")

    def test_reject_decision_rejects_the_roll(self):
        roll = self.make_roll("RT-REJ")
        insp = self._inspection(roll)
        insp.write({"result_override": "reject", "reason": "Holes across the width"})
        insp.action_done()
        self.assertEqual(roll.roll_status, "rejected")

    def test_reinspection_that_passes_releases_a_held_roll(self):
        roll = self.make_roll("RT-RE", status="hold")
        insp = self._inspection(roll)
        insp.action_done()
        self.assertEqual(roll.roll_status, "approved")

    def test_finish_needs_length_and_width(self):
        roll = self.make_roll("RT-NOLEN", width_cm=0)
        insp = self._inspection(roll, length=0.0, width=0.0)
        with self.assertRaises(UserError):
            insp.action_done()

    def test_finished_inspection_is_locked_on_the_tablet_until_reopened(self):
        roll = self.make_roll("RT-LOCK")
        insp = self._inspection(roll)
        insp.action_done()
        defect = self.env["garment.defect"].search([], limit=1)
        with self.assertRaises(UserError):
            insp.tablet_add_defect(defect.id, "1", 4)
        insp.action_reopen()
        state = insp.tablet_add_defect(defect.id, "1", 4)
        self.assertEqual(state["penalty_points"], 1)

    def test_tablet_undo_removes_the_last_defect(self):
        insp = self._inspection(self.make_roll("RT-UNDO"))
        self._defects(insp, [(1, "1"), (2, "3")])
        state = insp.tablet_undo()
        self.assertEqual(state["penalty_points"], 1)
        self.assertEqual(state["result"], "pass")

    def test_inspection_defaults_from_the_roll(self):
        roll = self.make_roll("RT-DEF", qty=91.44, width_cm=152.4)
        insp = self.env["garment.fabric.inspection"].create({"lot_id": roll.id})
        self.assertAlmostEqual(insp.inspected_length_yd, 100.0, places=2)
        self.assertAlmostEqual(insp.cuttable_width_in, 60.0, places=2)
        self.assertTrue(insp.name.startswith("FI/"))

    def test_fabric_store_user_runs_an_inspection(self):
        roll = self.make_roll("RT-STORE")
        insp = self.env["garment.fabric.inspection"].with_user(self.store).create({
            "lot_id": roll.id, "inspected_length_yd": 100, "cuttable_width_in": 57.5})
        insp.tablet_add_defect(False, "2", 3)
        insp.tablet_finish()
        self.assertEqual(roll.roll_status, "approved")

    def test_start_relaxation_marks_the_roll_relaxing(self):
        roll = self.make_roll("RT-RELAX")
        self.assertEqual(roll.relaxation_status, "free")
        roll.action_start_relaxation()
        self.assertEqual(roll.relaxation_status, "relaxing")
