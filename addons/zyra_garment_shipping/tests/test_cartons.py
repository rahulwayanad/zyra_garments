from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import ShippingCase


@tagged("post_install", "-at_install", "zyra")
class TestCartons(ShippingCase):

    def test_assorted_pack_cartons_follow_the_ratio_per_colour(self):
        order = self.make_order(qty_per_cell=10)  # 2 colours × 3 sizes × 10 = 60
        plan = self.make_plan(order, ratio={self.s: 2, self.m: 2, self.l: 1})
        self.assertEqual(plan.pieces_per_carton, 5)
        # per colour: S and M empty after 5 cartons, L after 10 → 10 cartons per colour
        self.assertEqual(plan.cartons_planned, 20)
        plan.action_generate_cartons()
        self.assertEqual(len(plan.carton_ids), 20)
        self.assertEqual(sum(plan.carton_ids.mapped("pieces")), 60)
        first = plan.carton_ids.sorted("number")[0]
        self.assertEqual(first.name, "CTN 001")
        self.assertEqual(first.content, "S 2 · M 2 · L 1")
        self.assertTrue(first.colour_id)

    def test_solid_pack_puts_one_colour_and_size_per_carton_with_a_short_last_carton(self):
        order = self.make_order(qty_per_cell=10)
        plan = self.make_plan(order, kind="solid", ppc=4)
        self.assertEqual(plan.cartons_planned, 6 * 3)  # 10 = 4 + 4 + 2 per cell
        plan.action_generate_cartons()
        self.assertEqual(sorted(set(plan.carton_ids.mapped("pieces"))), [2, 4])

    def test_ratio_pack_mixes_colours_and_needs_a_colour_per_ratio_line(self):
        order = self.make_order(qty_per_cell=6)
        plan = self.make_plan(order, kind="ratio", ratio={(self.red, self.m): 3, (self.blue, self.m): 3})
        self.assertEqual(plan.cartons_planned, 2)
        plan.action_generate_cartons()
        self.assertFalse(plan.carton_ids[0].colour_id)  # mixed carton
        with self.assertRaises(ValidationError):
            self.make_plan(order, kind="ratio", ratio={self.m: 3})

    def test_carton_weights_and_volume(self):
        plan = self.make_plan(self.make_order(), ratio={self.s: 6, self.m: 6, self.l: 6})
        plan.action_generate_cartons()
        carton = plan.carton_ids[0]
        self.assertEqual(carton.pieces, 18)
        self.assertAlmostEqual(carton.net_weight, 18 * 0.59)
        self.assertAlmostEqual(carton.gross_weight, 18 * 0.59 + 0.95)
        self.assertAlmostEqual(carton.cbm, 0.06)
        # plan totals: net on pieces planned, gross adds the empty cartons, volume per planned carton
        self.assertAlmostEqual(plan.net_weight, 60 * 0.59)
        self.assertAlmostEqual(plan.gross_weight, 60 * 0.59 + plan.cartons_planned * 0.95)
        self.assertAlmostEqual(plan.volume_cbm, plan.cartons_planned * 0.06)

    def test_generate_more_cartons_only_adds_the_missing_ones(self):
        order = self.make_order()
        plan = self.make_plan(order)
        plan.action_generate_cartons()
        plan.action_generate_cartons()
        self.assertEqual(len(plan.carton_ids), plan.cartons_planned)
        order.action_amend()
        order.line_ids[0].qty_ordered = 20
        plan.invalidate_recordset()
        plan.action_generate_cartons()
        self.assertEqual(len(plan.carton_ids), plan.cartons_planned)
        self.assertEqual(len(set(plan.carton_ids.mapped("number"))), len(plan.carton_ids))

    def test_packing_posts_packed_progress_to_the_order(self):
        order = self.make_order()
        plan = self.make_plan(order)
        plan.action_generate_cartons()
        cartons = plan.carton_ids.sorted("number")[:3]
        cartons.with_user(self.packer).action_pack()
        self.assertEqual(order.qty_packed, 15)
        postings = order.progress_ids.filtered(lambda p: p.stage == "packed")
        self.assertTrue(all(p.ref.startswith(plan.name + " CTN 001–003") for p in postings))
        self.assertEqual(plan.state, "packing")
        self.assertEqual(plan.cartons_packed, 3)
        self.assertEqual(plan.pieces_packed, 15)
        self.assertEqual(order.garment_cartons_packed, 3)
        self.assertEqual(order.garment_cartons_planned, plan.cartons_planned)

    def test_unpacking_reverses_the_packed_progress(self):
        order = self.make_order()
        plan = self.make_plan(order)
        plan.action_generate_cartons()
        carton = plan.carton_ids[0]
        carton.action_pack()
        carton.action_unpack()
        self.assertEqual(order.qty_packed, 0)
        self.assertEqual(carton.state, "planned")

    def test_a_packed_carton_cannot_be_packed_again_or_edited(self):
        plan = self.make_plan(self.make_order())
        plan.action_generate_cartons()
        carton = plan.carton_ids[0]
        carton.action_pack()
        with self.assertRaises(UserError):
            carton.action_pack()
        with self.assertRaises(UserError):
            carton.line_ids[0].carton_id.write({"line_ids": [(5, 0, 0)]})

    def test_plan_is_packed_when_every_planned_carton_is_packed(self):
        order = self.make_order()
        plan = self.make_plan(order)
        wiz = self.env["garment.carton.pack.wizard"].create({"plan_id": plan.id, "count": 100})
        wiz.action_pack()
        self.assertEqual(plan.state, "packed")
        self.assertEqual(order.qty_packed, 60)
        self.assertAlmostEqual(plan.cartons_packed_pct, 100.0)

    def test_post_to_stock_makes_one_manufacturing_order_per_variant_for_exactly_the_packed_quantity(self):
        order = self.make_order()
        plan = self.make_plan(order)
        plan.action_generate_cartons()
        cartons = plan.carton_ids.sorted("number")[:2]  # one colour, 2 × (S2 M2 L1)
        cartons.action_pack()
        self.assertEqual(plan.pieces_waiting_stock, 10)
        plan.action_post_to_stock()
        mos = plan.production_ids
        self.assertEqual(len(mos), 3)
        self.assertTrue(all(mo.state == "done" for mo in mos))
        qty = {mo.product_id.garment_size_id: mo.product_qty for mo in mos}
        self.assertEqual(qty, {self.s: 4, self.m: 4, self.l: 2})
        self.assertEqual(plan.pieces_waiting_stock, 0)
        self.assertTrue(all(cartons.mapped("stock_posted")))
        with self.assertRaises(UserError):
            plan.action_post_to_stock()

    def test_order_form_pack_plan_button_opens_or_creates_the_plan(self):
        order = self.make_order()
        action = order.action_garment_pack_plan()
        self.assertFalse(action.get("res_id"))
        plan = self.make_plan(order)
        self.assertEqual(order.action_garment_pack_plan()["res_id"], plan.id)

    def test_packing_list_groups_consecutive_cartons_with_the_same_content(self):
        plan = self.make_plan(self.make_order())
        plan.action_generate_cartons()
        plan.carton_ids.action_pack()
        data = self.env["garment.carton"]._packing_list_rows(plan.carton_ids)
        self.assertEqual(data["pieces"], 60)
        self.assertEqual(data["cartons"], 20)
        self.assertEqual(sum(r["pieces"] for r in data["rows"]), 60)
        self.assertEqual(data["rows"][0]["range"], "1 – 5")
        html = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_shipping.report_pack_plan_packing_list", plan.ids)[0]
        self.assertIn(b"Packing List", html)
