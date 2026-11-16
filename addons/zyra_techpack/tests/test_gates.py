from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import TechpackCase


@tagged("post_install", "-at_install", "zyra")
class TestGates(TechpackCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.style._ensure_product()
        cls.variant = cls.style._get_variant(cls.navy, cls.m)
        cls.customer = cls.buyer

    def _sale_order(self):
        return self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({"product_id": self.variant.id, "product_uom_qty": 10})],
        })

    def test_sale_order_with_unapproved_style_cannot_be_confirmed(self):
        order = self._sale_order()
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, "draft")

    def test_sale_order_with_approved_style_confirms_and_records_tech_pack(self):
        self.approve(self.techpack)
        order = self._sale_order()
        order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.order_line.techpack_id, self.techpack)
        self.assertEqual(self.techpack.sale_order_count, 1)

    def test_sale_order_without_garment_products_is_not_gated(self):
        product = self.env["product.product"].create({"name": "Service", "type": "service"})
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
        })
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def _production(self):
        form = Form(self.env["mrp.production"])
        form.product_id = self.variant
        form.product_qty = 5
        return form.save()

    def test_manufacturing_order_with_unapproved_style_cannot_be_confirmed(self):
        production = self._production()
        with self.assertRaises(UserError):
            production.action_confirm()
        self.assertEqual(production.state, "draft")

    def test_manufacturing_order_with_approved_style_uses_current_tech_pack(self):
        self.approve(self.techpack)
        production = self._production()
        self.assertEqual(production.techpack_id, self.techpack)
        self.assertEqual(production.bom_id, self.techpack.bom_id)
        production.action_confirm()
        self.assertEqual(production.state, "confirmed")
        self.assertEqual(len(production.move_raw_ids), 2, "navy fabric + label for a size M")

    def test_manufacturing_order_on_superseded_tech_pack_cannot_be_confirmed(self):
        self.approve(self.techpack)
        production = self._production()
        v2 = self.env["zyra.techpack"].browse(self.techpack.action_new_revision()["res_id"])
        self.approve(v2)
        with self.assertRaises(UserError):
            production.action_confirm()
        production.techpack_id = v2
        production.action_confirm()
        self.assertEqual(production.state, "confirmed")

    def test_tech_pack_passes_from_sale_order_to_generated_manufacturing_order(self):
        mto = self.env.ref("stock.route_warehouse0_mto")
        mto.active = True
        manufacture = self.env.ref("mrp.route_warehouse0_manufacture")
        self.style.product_tmpl_id.route_ids = [Command.set([mto.id, manufacture.id])]
        self.approve(self.techpack)
        order = self._sale_order()
        order.action_confirm()
        production = self.env["mrp.production"].search([("origin", "=", order.name)])
        self.assertEqual(len(production), 1)
        self.assertEqual(production.techpack_id, self.techpack)
        self.assertEqual(production.bom_id, self.techpack.bom_id)
        self.assertEqual(self.techpack.production_count, 1)
