from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestProgressApi(MerchCase):

    def test_progress_adds_pieces_to_the_cell_and_the_order(self):
        order = self.make_order()
        posting = order._garment_add_progress("cut", self.red.id, self.m.id, 7, ref="LAY-1")
        self.assertEqual(posting._name, "garment.order.progress")
        self.assertEqual((posting.stage, posting.qty, posting.ref), ("cut", 7, "LAY-1"))
        line = order.line_ids.filtered(lambda l: l.colour_id == self.red and l.size_id == self.m)
        self.assertEqual(line.qty_cut, 7)
        order._garment_add_progress("cut", self.red, self.m, 3)  # records accepted too
        self.assertEqual(line.qty_cut, 10)
        self.assertEqual(order.qty_cut, 10)
        self.assertEqual(order.posting_count, 2)

    def test_each_stage_has_its_own_total(self):
        order = self.make_order()
        for stage, qty in (("cut", 10), ("sewn", 8), ("packed", 6), ("shipped", 4)):
            order._garment_add_progress(stage, self.blue.id, self.l.id, qty)
        line = order.line_ids.filtered(lambda l: l.colour_id == self.blue and l.size_id == self.l)
        self.assertEqual((line.qty_cut, line.qty_sewn, line.qty_packed, line.qty_shipped, line.qty_balance),
                         (10, 8, 6, 4, 6))
        self.assertEqual(order.qty_balance, 60 - 4)
        self.assertAlmostEqual(order.packed_pct, 10.0)

    def test_negative_posting_corrects_but_never_below_zero(self):
        order = self.make_order()
        order._garment_add_progress("sewn", self.red.id, self.s.id, 5)
        order._garment_add_progress("sewn", self.red.id, self.s.id, -2)
        self.assertEqual(order.qty_sewn, 3)
        with self.assertRaises(ValidationError):
            order._garment_add_progress("sewn", self.red.id, self.s.id, -4)

    def test_unknown_stage_is_refused(self):
        order = self.make_order()
        with self.assertRaises(ValidationError):
            order._garment_add_progress("ironed", self.red.id, self.s.id, 1)

    def test_quantity_must_be_a_non_zero_whole_number(self):
        order = self.make_order()
        for bad in (0, 1.5, "3", True):
            with self.assertRaises(ValidationError):
                order._garment_add_progress("cut", self.red.id, self.s.id, bad)
        order._garment_add_progress("cut", self.red.id, self.s.id, 2.0)
        self.assertEqual(order.qty_cut, 2)

    def test_draft_order_refuses_progress(self):
        order = self.make_order(confirm=False)
        with self.assertRaises(UserError):
            order._garment_add_progress("cut", self.red.id, self.s.id, 1)

    def test_cell_not_in_the_grid_is_refused(self):
        order = self.make_order()
        other = self.env["garment.colour"].create({"name": "Merch Green"})
        with self.assertRaises(UserError):
            order._garment_add_progress("cut", other.id, self.s.id, 1)

    def test_first_pieces_put_the_order_in_production(self):
        order = self.make_order()
        order._garment_add_progress("cut", self.red.id, self.s.id, 1)
        self.assertEqual(order.state, "in_production")

    def test_order_becomes_packed_then_shipped_when_every_piece_is(self):
        order = self.make_order({(self.red, self.s): 4, (self.blue, self.l): 6})
        for colour, size, qty in ((self.red, self.s, 4), (self.blue, self.l, 6)):
            order._garment_add_progress("cut", colour, size, qty)
            order._garment_add_progress("packed", colour, size, qty)
        self.assertEqual(order.state, "packed")
        order._garment_add_progress("shipped", self.red, self.s, 4)
        self.assertEqual(order.state, "packed")
        order._garment_add_progress("shipped", self.blue, self.l, 6)
        self.assertEqual(order.state, "shipped")

    def test_floor_role_can_post_progress_without_order_write_rights(self):
        order = self.make_order()
        order.with_user(self.cutter)._garment_add_progress("cut", self.red.id, self.s.id, 3)
        self.assertEqual(order.qty_cut, 3)
        self.assertEqual(order.progress_ids.user_id, self.cutter)

    def test_postings_cannot_be_edited(self):
        order = self.make_order()
        posting = order._garment_add_progress("cut", self.red.id, self.s.id, 3)
        with self.assertRaises(UserError):
            posting.qty = 30

    def test_closed_order_refuses_progress(self):
        order = self.make_order()
        order.with_user(self.manager).action_close()
        with self.assertRaises(UserError):
            order._garment_add_progress("shipped", self.red.id, self.s.id, 1)
