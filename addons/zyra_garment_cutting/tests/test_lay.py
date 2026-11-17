from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CuttingCase


@tagged("post_install", "-at_install", "zyra")
class TestLay(CuttingCase):

    def _approved_plan(self, **vals):
        plan = self.make_plan(**vals)
        plan.action_propose()
        plan.action_approve()
        return plan

    def _first_lay(self, plan):
        return plan.lay_ids.sorted("lay_no")[0]

    def test_fabric_laid_and_end_loss_formula(self):
        plan = self._approved_plan(end_allowance_m=0.04)
        lay = self._first_lay(plan)
        lay.roll_line_ids = [Command.create({"lot_id": self.roll_a.id, "plies": 48})]
        self.assertEqual(lay.plies_actual, 48)
        self.assertEqual(lay.pieces, 48 * 4)
        self.assertAlmostEqual(lay.fabric_laid, 48 * (4.0 + 0.04), places=2)
        self.assertAlmostEqual(lay.end_loss_pct, 100 * 48 * 0.04 / (48 * 4.04), places=2)

    def test_only_approved_rolls_may_be_laid(self):
        lay = self._first_lay(self._approved_plan())
        with self.assertRaises(ValidationError):
            lay.roll_line_ids = [Command.create({"lot_id": self.roll_hold.id, "plies": 10})]

    def test_roll_put_on_hold_after_spreading_blocks_the_cut(self):
        lay = self._first_lay(self._approved_plan())
        lay.roll_line_ids = [Command.create({"lot_id": self.roll_b.id, "plies": 80})]
        self.roll_b.action_roll_hold("Late shade complaint")
        with self.assertRaises(UserError):
            lay.action_cut()

    def test_cutting_a_lay_posts_cut_progress_per_size(self):
        lay = self._first_lay(self._approved_plan())
        self.cut_lay(lay)
        self.assertEqual(lay.state, "cut")
        grid = self.order._garment_get_grid()
        self.assertEqual(grid[(self.red.id, self.s.id)]["cut"], 80)
        self.assertEqual(grid[(self.red.id, self.m.id)]["cut"], 160)
        self.assertEqual(grid[(self.red.id, self.l.id)]["cut"], 80)
        self.assertEqual(self.order.qty_cut, 320)
        postings = self.order.progress_ids.filtered(lambda p: p.stage == "cut")
        self.assertEqual(set(postings.mapped("ref")), {lay.name})
        self.assertEqual(self.order.state, "in_production")

    def test_cutting_a_lay_consumes_fabric_from_its_rolls(self):
        plan = self._approved_plan(end_allowance_m=0.04)
        lay = self._first_lay(plan)
        before_a = self.roll_a._garment_roll_available()
        before_b = self.roll_b._garment_roll_available()
        self.cut_lay(lay, [(self.roll_a, 50), (self.roll_b, 30)])
        self.assertAlmostEqual(before_a - self.roll_a._garment_roll_available(), 50 * 4.04, places=2)
        self.assertAlmostEqual(before_b - self.roll_b._garment_roll_available(), 30 * 4.04, places=2)
        self.assertEqual(len(lay.move_ids), 2)
        self.assertTrue(all(m.state == "done" for m in lay.move_ids))

    def test_cut_refused_when_a_roll_has_not_enough_fabric(self):
        lay = self._first_lay(self._approved_plan())
        lay.roll_line_ids = [Command.create({"lot_id": self.roll_small.id, "plies": 5})]
        with self.assertRaises(UserError):
            lay.action_cut()
        self.assertEqual(self.order.qty_cut, 0)

    def test_cut_needs_rolls_and_an_approved_plan(self):
        plan = self._approved_plan()
        lay = self._first_lay(plan)
        with self.assertRaises(UserError):
            lay.action_cut()

    def test_mixed_shades_are_flagged_on_the_lay(self):
        lay = self._first_lay(self._approved_plan())
        lay.roll_line_ids = [Command.create({"lot_id": self.roll_a.id, "plies": 40, "sequence": 1}),
                             Command.create({"lot_id": self.roll_b.id, "plies": 40, "sequence": 2})]
        self.assertTrue(lay.mixed_shades)
        self.assertEqual(lay.shades, "A, B")

    def test_ply_numbers_run_on_from_roll_to_roll(self):
        lay = self._first_lay(self._approved_plan())
        lay.roll_line_ids = [Command.create({"lot_id": self.roll_a.id, "plies": 30, "sequence": 1}),
                             Command.create({"lot_id": self.roll_b.id, "plies": 50, "sequence": 2})]
        first, second = lay.roll_line_ids.sorted("sequence")
        self.assertEqual((first.ply_from, first.ply_to), (1, 30))
        self.assertEqual((second.ply_from, second.ply_to), (31, 80))

    def test_cut_lay_cannot_change_rolls_or_be_deleted(self):
        lay = self.cut_lay(self._first_lay(self._approved_plan()))
        with self.assertRaises(UserError):
            lay.roll_line_ids.plies = 10
        with self.assertRaises(UserError):
            lay.unlink()
        with self.assertRaises(UserError):
            lay.action_cancel()

    def test_plan_moves_to_cutting_then_done_when_all_lays_are_bundled(self):
        plan = self._approved_plan()
        lays = plan.lay_ids.sorted("lay_no")
        self.cut_lay(lays[0])
        self.assertEqual(plan.state, "cutting")
        self.assertEqual(plan.qty_cut, 320)
        for lay in lays[1:]:
            self.cut_lay(lay)
        for lay in lays:
            lay.action_create_bundles()
        self.assertEqual(plan.lays_bundled, plan.lay_count)
        self.assertEqual(plan.state, "done")
        self.assertEqual(plan.qty_cut, plan.qty_to_cut)

    def test_return_end_bits_records_the_metres(self):
        lay = self.cut_lay(self._first_lay(self._approved_plan()))
        wizard = self.env["garment.lay.end.bits"].create({"lay_id": lay.id, "end_bits_m": 2.5})
        wizard.action_confirm()
        self.assertEqual(lay.end_bits_m, 2.5)

    def test_cutting_role_can_cut_without_stock_rights(self):
        plan = self._approved_plan()
        lay = self._first_lay(plan).with_user(self.cutter)
        lay.roll_line_ids = [Command.create({"lot_id": self.roll_a.id, "plies": 80})]
        lay.action_cut()
        lay.action_create_bundles()
        self.assertEqual(lay.state, "bundled")
        self.assertEqual(self.order.qty_cut, 320)
