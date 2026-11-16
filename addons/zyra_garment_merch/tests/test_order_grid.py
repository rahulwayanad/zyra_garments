from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestOrderGrid(MerchCase):

    def test_new_order_grid_has_one_cell_per_colourway_and_size(self):
        order = self.make_order(confirm=False)
        self.assertEqual(len(order.line_ids), 6)
        cells = {(l.colour_id, l.size_id) for l in order.line_ids}
        self.assertEqual(cells, {(c, s) for c in (self.red, self.blue) for s in (self.s, self.m, self.l)})
        self.assertEqual(order.techpack_id, self.techpack, "the current approved tech pack is taken")
        self.assertEqual(order.buyer_id, self.buyer)

    def test_order_form_builds_grid_when_style_is_chosen(self):
        with Form(self.env["garment.order"]) as form:
            form.style_id = self.style
            form.ex_factory_date = self.today + timedelta(days=30)
            self.assertEqual(len(form.line_ids), 6)
            with form.line_ids.edit(0) as line:
                line.qty_ordered = 25
        order = form.record
        self.assertEqual(len(order.line_ids), 6)
        self.assertEqual(order.qty_ordered, 25)

    def test_grid_totals_and_order_value(self):
        qty = {(self.red, self.s): 10, (self.red, self.m): 20, (self.red, self.l): 30,
               (self.blue, self.s): 5, (self.blue, self.m): 5, (self.blue, self.l): 0}
        order = self.make_order(qty, confirm=False, price_unit=4.0)
        self.assertEqual(order.qty_ordered, 70)
        self.assertEqual(order.order_value, 280.0)
        self.assertEqual(order.qty_balance, 70)
        self.assertEqual(sum(order.line_ids.filtered(lambda l: l.colour_id == self.red).mapped("qty_ordered")), 60)

    def test_removing_a_colourway_drops_its_empty_cells(self):
        order = self.make_order(confirm=False)
        with Form(order) as form:
            form.colour_ids.remove(id=self.blue.id)
        self.assertEqual(order.line_ids.colour_id, self.red)
        self.assertEqual(len(order.line_ids), 3)

    def test_confirm_needs_quantities_in_the_grid(self):
        order = self.make_order({(self.red, self.s): 0}, confirm=False)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_confirm_needs_style_approved_for_production(self):
        order = self.env["garment.order"].create({
            "style_id": self.open_style.id, "ex_factory_date": self.today + timedelta(days=30)})
        order.line_ids[:1].qty_ordered = 10
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_confirmed_grid_changes_only_through_amend_order(self):
        order = self.make_order()
        self.assertEqual(order.state, "confirmed")
        with self.assertRaises(UserError):
            order.line_ids[0].qty_ordered = 99
        order.action_amend()
        order.line_ids[0].qty_ordered = 99
        order.action_done_amending()
        self.assertFalse(order.is_amending)
        self.assertEqual(order.qty_ordered, 99 + 50)

    def test_ex_factory_cannot_be_before_order_date(self):
        with self.assertRaises(ValidationError):
            self.make_order(confirm=False, ex_days=-100)

    def test_size_outside_the_style_range_is_refused(self):
        other = self.env["garment.size.range"].create({"name": "Other", "size_ids": [Command.create({"name": "XX"})]})
        order = self.make_order(confirm=False)
        with self.assertRaises(ValidationError):
            order.line_ids = [Command.create({"colour_id": self.red.id, "size_id": other.size_ids.id})]

    def test_only_factory_manager_closes_an_order_short(self):
        order = self.make_order()
        with self.assertRaises(UserError):
            order.with_user(self.merchandiser).action_close()
        order.with_user(self.manager).action_close()
        self.assertEqual(order.state, "closed")

    def test_mark_completed_needs_everything_shipped(self):
        order = self.make_order({(self.red, self.s): 5})
        with self.assertRaises(UserError):
            order.action_mark_completed()
        order._garment_add_progress("shipped", self.red, self.s, 5)
        order.action_mark_completed()
        self.assertEqual(order.state, "closed")

    def test_confirmed_order_cannot_be_deleted(self):
        order = self.make_order()
        with self.assertRaises(UserError):
            order.unlink()

    def test_confirming_a_sale_order_opens_the_production_order_with_its_grid(self):
        self.style.action_generate_variants_bom()
        variant_rs = self.style._get_variant(self.red, self.s)
        variant_bm = self.style._get_variant(self.blue, self.m)
        self.assertTrue(variant_rs and variant_bm)
        so = self.env["sale.order"].create({
            "partner_id": self.buyer.id,
            "client_order_ref": "PO-BUYER-1",
            "order_line": [
                Command.create({"product_id": variant_rs.id, "product_uom_qty": 120, "price_unit": 5.0}),
                Command.create({"product_id": variant_bm.id, "product_uom_qty": 80, "price_unit": 6.0}),
            ],
        })
        so.action_confirm()
        order = so.garment_order_ids
        self.assertEqual(len(order), 1)
        self.assertEqual(order.state, "confirmed")
        self.assertEqual(order.style_id, self.style)
        self.assertEqual(order.buyer_po, "PO-BUYER-1")
        self.assertEqual(order.qty_ordered, 200)
        grid = order._garment_get_grid()
        self.assertEqual(grid[(self.red.id, self.s.id)]["ordered"], 120)
        self.assertEqual(grid[(self.blue.id, self.m.id)]["ordered"], 80)
        self.assertAlmostEqual(order.price_unit, (600 + 480) / 200)
        self.assertEqual(so.garment_order_count, 1)
