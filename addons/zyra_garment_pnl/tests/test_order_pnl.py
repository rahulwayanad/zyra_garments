from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "zyra")
class TestOrderPnl(TransactionCase):
    """One order end to end with known numbers.

    Order: 2 colours × 3 sizes × 10 = 60 pieces at 5.00 → order value 300.
    Cost sheet (approved): fabric 1.0 × 2.50 = 2.50/pc, making 10 SAM × 0.05 ÷ 50 % = 1.00/pc,
    other (process) 0.50/pc → planned 4.00/pc × 60 shipped = 240.
    Actual: material issued 50 × 2.00 = 100, job work 60 × 0.50 = 30, other cost 20, sample not charged 10
    → 160. Invoiced 300 → margin 140 (46.67 %), planned margin 20 %, variance −80, cost/pc 2.67.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.today = fields.Date.context_today(env["garment.order"])
        cls.manager = new_test_user(env, "pnl_fm", groups="zyra_garment_base.group_garment_factory_manager,"
                                                           "zyra_garment_base.group_garment_costing")
        size_range = env["garment.size.range"].create({
            "name": "PnL S-L",
            "size_ids": [Command.create({"name": n, "sequence": i * 10}) for i, n in enumerate(["S", "M", "L"])],
        })
        cls.sizes = size_range.size_ids.sorted("sequence")
        cls.red = env["garment.colour"].create({"name": "PnL Red", "code": "PRD", "hex": "#AA2233"})
        cls.blue = env["garment.colour"].create({"name": "PnL Blue", "code": "PBL", "hex": "#2233AA"})
        cls.buyer = env["res.partner"].create({"name": "PnL Test Buyer", "is_garment_buyer": True})
        unit = env.ref("uom.product_uom_unit")
        cls.fabric = env["product.product"].create({
            "name": "PnL Fabric", "is_storable": True, "uom_id": unit.id, "uom_po_id": unit.id,
            "standard_price": 2.0})
        cls.style = env["garment.style"].create({
            "name": "PnL Tee", "code": "PNL-01", "buyer_id": cls.buyer.id, "size_range_id": size_range.id,
            "colour_ids": [Command.set([cls.red.id, cls.blue.id])],
        })
        techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id, "base_size_id": cls.sizes[1].id,
            "bom_line_ids": [Command.create({"product_id": cls.fabric.id, "material_kind": "fabric",
                                             "consumption": 1.0, "wastage_pct": 0.0, "price_unit": 2.5})],
        })
        techpack.sudo().action_submit()
        techpack.sudo().action_approve()
        sheet = env["garment.cost.sheet"].create({
            "techpack_id": techpack.id, "quantity_basis": 60, "sam": 10.0, "cost_per_minute": 0.05,
            "line_efficiency": 50.0, "overhead_pct": 0.0, "commission_pct": 0.0, "margin_pct": 20.0,
            "freight_pc": 0.0,
            "process_line_ids": [Command.create({"process_type": "other", "name": "Testing",
                                                 "charge_basis": "piece", "cost": 0.5})],
        })
        if not sheet.material_line_ids:
            sheet.action_load_from_techpack()
        sheet.action_submit()
        sheet.with_user(cls.manager)._do_approve(reason="test")
        cls.sheet = sheet
        cls.vendor = env["res.partner"].create({"name": "PnL Stitch House", "is_jobwork_vendor": True})

    def _order(self, qty=10, price=5.0):
        order = self.env["garment.order"].create({
            "style_id": self.style.id, "buyer_id": self.buyer.id, "price_unit": price,
            "date_order": self.today - timedelta(days=30), "ex_factory_date": self.today + timedelta(days=10),
        })
        for line in order.line_ids:
            line.qty_ordered = qty
        order.action_confirm()
        return order

    def _ship_all(self, order):
        for line in order.line_ids:
            order._garment_add_progress("shipped", line.colour_id, line.size_id, line.qty_ordered, ref="test")

    def _invoice(self, order, qty, price, move_type="out_invoice", post=True):
        move = self.env["account.move"].create({
            "move_type": move_type, "partner_id": self.buyer.id,
            "invoice_line_ids": [Command.create({"name": "Pieces", "quantity": qty, "price_unit": price,
                                                 "garment_order_id": order.id, "tax_ids": [Command.clear()]})],
        })
        if post:
            move.action_post()
        return move

    def _issue_material(self, order, qty):
        stock = self.env.ref("stock.warehouse0").lot_stock_id
        move = self.env["stock.move"].create({
            "name": "Issue to order", "product_id": self.fabric.id, "product_uom_qty": qty,
            "product_uom": self.fabric.uom_id.id, "location_id": stock.id,
            "location_dest_id": self.env.ref("stock.stock_location_production").id
            if self.env.ref("stock.stock_location_production", raise_if_not_found=False)
            else self.fabric.property_stock_production.id,
            "garment_pnl_order_id": order.id,
        })
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def _jobwork(self, order, qty, rate):
        jw = self.env["garment.jobwork.order"].create({
            "vendor_id": self.vendor.id, "process": "sewing", "qty_sent": qty, "rate": rate,
            "production_order_id": order.id, "date_expected": self.today + timedelta(days=5)})
        jw.action_send()
        jw._garment_receive(qty)
        jw.action_bill()
        return jw

    def test_planned_cost_comes_from_the_approved_cost_sheet(self):
        order = self._order()
        self.assertAlmostEqual(order.planned_material_pc, 2.5)
        self.assertAlmostEqual(order.planned_making_pc, 1.0)
        self.assertAlmostEqual(order.planned_other_pc, 0.5)

    def test_one_order_end_to_end_gives_expected_margin_and_variance(self):
        order = self._order()
        self._ship_all(order)
        self._invoice(order, 60, 5.0)
        self._invoice(order, 10, 5.0, post=False)  # draft invoice: not revenue yet
        self._issue_material(order, 50)
        self._jobwork(order, 60, 0.5)
        self.env["garment.sample"].create({
            "style_id": self.style.id, "order_id": order.id, "buyer_id": self.buyer.id,
            "sample_type": "pp", "cost": 10.0, "charge_to_buyer": False})
        pnl = order._garment_pnl()
        pnl.cost_line_ids = [Command.create({"name": "Courier", "amount": 20.0})]
        pnl.action_refresh()
        self.assertEqual(pnl.qty_ordered, 60)
        self.assertEqual(pnl.pieces_costed, 60)
        self.assertAlmostEqual(pnl.order_value, 300.0)
        self.assertAlmostEqual(pnl.revenue, 300.0)
        self.assertAlmostEqual(pnl.planned_material, 150.0)
        self.assertAlmostEqual(pnl.planned_making, 60.0)
        self.assertAlmostEqual(pnl.planned_other, 30.0)
        self.assertAlmostEqual(pnl.planned_cost, 240.0)
        self.assertAlmostEqual(pnl.actual_material, 100.0)
        self.assertAlmostEqual(pnl.actual_making, 0.0)
        self.assertAlmostEqual(pnl.actual_jobwork, 30.0)
        self.assertAlmostEqual(pnl.actual_other, 30.0)
        self.assertAlmostEqual(pnl.actual_cost, 160.0)
        self.assertAlmostEqual(pnl.margin, 140.0)
        self.assertAlmostEqual(pnl.margin_pct, 46.67)
        self.assertAlmostEqual(pnl.planned_margin_pct, 20.0)
        self.assertAlmostEqual(pnl.cost_variance, -80.0)
        self.assertAlmostEqual(pnl.cost_pc, 2.67, places=2)
        self.assertAlmostEqual(pnl.revenue_pc, 5.0)
        self.assertFalse(pnl.is_loss)
        self.assertEqual(pnl.name, "%s · PNL-01" % order.name)

    def test_credit_note_reduces_invoiced_revenue(self):
        order = self._order()
        self._invoice(order, 60, 5.0)
        self._invoice(order, 4, 5.0, move_type="out_refund")
        pnl = order._garment_pnl()
        self.assertAlmostEqual(pnl.revenue, 280.0)

    def test_pieces_costed_are_shipped_pieces_else_ordered(self):
        order = self._order()
        pnl = order._garment_pnl()
        self.assertEqual(pnl.pieces_costed, 60)
        line = order.line_ids[0]
        order._garment_add_progress("shipped", line.colour_id, line.size_id, 10)
        pnl.action_refresh()
        self.assertEqual(pnl.pieces_costed, 10)
        self.assertAlmostEqual(pnl.planned_cost, 40.0)

    def test_cost_above_revenue_is_a_loss(self):
        order = self._order()
        self._invoice(order, 60, 1.0)
        self._issue_material(order, 50)
        pnl = order._garment_pnl()
        self.assertAlmostEqual(pnl.margin, -40.0)
        self.assertTrue(pnl.is_loss)
        summary = self.env["garment.order.pnl"]._garment_profit_summary([("id", "=", pnl.id)])
        self.assertEqual(summary["loss_count"], 1)
        self.assertAlmostEqual(summary["margin_pct"], -66.6666, places=2)

    def test_formula_matches_screen_75(self):
        """Screen 75: 352 pieces, invoiced 1,724.80, planned 2.74 + 0.30 + 0.26 / pc, actual 1,272.55."""
        figures = self.env["garment.order.pnl"]._pnl_figures({
            "pieces_costed": 352, "revenue": 1724.80, "planned_material_pc": 2.74,
            "planned_making_pc": 0.30, "planned_other_pc": 0.26,
            "material": 1000.0, "making": 120.55, "jobwork": 100.0, "other": 52.0})
        self.assertAlmostEqual(figures["planned_cost"], 1161.60)
        self.assertAlmostEqual(figures["actual_cost"], 1272.55)
        self.assertAlmostEqual(figures["margin"], 452.25)
        self.assertAlmostEqual(figures["margin_pct"], 26.22)
        self.assertAlmostEqual(figures["planned_margin_pct"], 32.65)
        self.assertAlmostEqual(figures["cost_variance"], 110.95)
        self.assertAlmostEqual(figures["cost_pc"], 3.615, places=3)
        self.assertAlmostEqual(figures["revenue_pc"], 4.90)

    def test_no_revenue_gives_zero_margin_percent(self):
        figures = self.env["garment.order.pnl"]._pnl_figures({"pieces_costed": 0, "material": 10.0})
        self.assertEqual(figures["margin_pct"], 0.0)
        self.assertEqual(figures["cost_pc"], 0.0)
        self.assertTrue(figures["is_loss"])

    def test_one_pnl_per_order(self):
        order = self._order()
        first = order._garment_pnl()
        self.assertEqual(order._garment_pnl(), first)
