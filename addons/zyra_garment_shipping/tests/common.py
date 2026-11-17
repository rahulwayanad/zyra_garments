from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class ShippingCase(TransactionCase):
    """One approved style (2 colourways × S/M/L, product variants and BoM) and an order of 10 per cell."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.today = fields.Date.context_today(env["garment.order"])
        cls.size_range = env["garment.size.range"].create({
            "name": "Ship Test S-L",
            "size_ids": [Command.create({"name": n, "sequence": i * 10}) for i, n in enumerate(["S", "M", "L"])],
        })
        cls.s, cls.m, cls.l = cls.size_range.size_ids.sorted("sequence")
        cls.red = env["garment.colour"].create({"name": "Ship Red", "code": "SRD", "hex": "#AA2233"})
        cls.blue = env["garment.colour"].create({"name": "Ship Blue", "code": "SBL", "hex": "#2233AA"})
        cls.buyer = env["res.partner"].create({"name": "Ship Test Buyer", "is_garment_buyer": True})
        unit = env.ref("uom.product_uom_unit")
        cls.fabric = env["product.product"].create({
            "name": "Ship Test Fabric", "type": "consu", "uom_id": unit.id, "uom_po_id": unit.id})
        cls.packer = new_test_user(env, "ship_packer", groups="zyra_garment_base.group_garment_packing_shipping")
        cls.manager = new_test_user(env, "ship_manager", groups="zyra_garment_base.group_garment_factory_manager")
        cls.style = env["garment.style"].create({
            "name": "Ship Test Tee", "code": "ZS-0001", "buyer_id": cls.buyer.id,
            "size_range_id": cls.size_range.id, "colour_ids": [Command.set([cls.red.id, cls.blue.id])],
        })
        techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id,
            "base_size_id": cls.m.id,
            "bom_line_ids": [Command.create({"product_id": cls.fabric.id, "material_kind": "fabric",
                                             "consumption": 1.0, "wastage_pct": 0.0, "price_unit": 2.5})],
        })
        techpack.sudo().action_submit()
        techpack.sudo().action_approve()

    def make_order(self, qty_per_cell=10, price=5.0):
        order = self.env["garment.order"].create({
            "style_id": self.style.id,
            "buyer_id": self.buyer.id,
            "ex_factory_date": self.today + timedelta(days=30),
            "date_order": self.today - timedelta(days=60),
            "price_unit": price,
        })
        for line in order.line_ids:
            line.qty_ordered = qty_per_cell
        order.action_confirm()
        return order

    def make_plan(self, order, kind="assorted", ratio=None, ppc=0, **vals):
        ratio = ratio if ratio is not None else {self.s: 2, self.m: 2, self.l: 1}
        lines = []
        for key, qty in ratio.items():
            colour, size = key if isinstance(key, tuple) else (None, key)
            lines.append(Command.create({"size_id": size.id, "qty": qty, "colour_id": colour.id if colour else False}))
        return self.env["garment.pack.plan"].create(dict({
            "order_id": order.id, "pack_kind": kind, "ratio_line_ids": lines if kind != "solid" else [],
            "pieces_per_carton": ppc, "length_cm": 60, "width_cm": 40, "height_cm": 25,
            "net_weight_per_piece": 0.59, "empty_carton_weight": 0.95,
        }, **vals))
