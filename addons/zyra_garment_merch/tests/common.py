from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class MerchCase(TransactionCase):
    """Self-contained data: one approved style (2 colourways × 3 sizes) and one open style."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.today = fields.Date.context_today(env["garment.order"])
        cls.size_range = env["garment.size.range"].create({
            "name": "Merch Test S-L",
            "size_ids": [Command.create({"name": n, "sequence": i * 10}) for i, n in enumerate(["S", "M", "L"])],
        })
        cls.s, cls.m, cls.l = cls.size_range.size_ids.sorted("sequence")
        cls.red = env["garment.colour"].create({"name": "Merch Red", "code": "MRD", "hex": "#AA2233"})
        cls.blue = env["garment.colour"].create({"name": "Merch Blue", "code": "MBL", "hex": "#2233AA"})
        cls.buyer = env["res.partner"].create({"name": "Merch Test Buyer", "is_garment_buyer": True})
        unit = env.ref("uom.product_uom_unit")
        cls.fabric = env["product.product"].create({
            "name": "Merch Test Fabric", "type": "consu", "uom_id": unit.id, "uom_po_id": unit.id})
        cls.pom_chest = env["garment.pom"].create({"code": "ZM01", "name": "Merch chest", "default_tolerance": 1.0})
        cls.pom_length = env["garment.pom"].create({"code": "ZM02", "name": "Merch length",
                                                    "default_tolerance": 1.5})
        cls.merchandiser = new_test_user(env, "merch_user", groups="zyra_garment_base.group_garment_merchandiser")
        cls.manager = new_test_user(env, "merch_manager", groups="zyra_garment_base.group_garment_factory_manager")
        cls.cutter = new_test_user(env, "merch_cutter", groups="zyra_garment_base.group_garment_cutting")

        cls.style = env["garment.style"].create({
            "name": "Merch Test Tee", "code": "ZM-0001", "buyer_id": cls.buyer.id,
            "size_range_id": cls.size_range.id, "colour_ids": [Command.set([cls.red.id, cls.blue.id])],
        })
        cls.techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id,
            "base_size_id": cls.m.id,
            "bom_line_ids": [
                Command.create({"product_id": cls.fabric.id, "material_kind": "fabric", "consumption": 1.0,
                                "wastage_pct": 0.0, "price_unit": 2.5}),
            ],
            "measurement_ids": [
                Command.create({"pom_id": cls.pom_chest.id, "base_value": 50.0, "grade_rule": 2.0,
                                "tol_plus": 1.0, "tol_minus": 1.0}),
                Command.create({"pom_id": cls.pom_length.id, "base_value": 70.0, "grade_rule": 1.5,
                                "tol_plus": 1.5, "tol_minus": 0.5}),
            ],
        })
        cls.techpack.sudo().action_submit()
        cls.techpack.sudo().action_approve()

        cls.open_style = env["garment.style"].create({
            "name": "Merch Test Shirt", "code": "ZM-0002", "buyer_id": cls.buyer.id,
            "size_range_id": cls.size_range.id, "colour_ids": [Command.set([cls.blue.id])],
        })
        cls.template = env["garment.tna.template"].create({
            "name": "Merch test template",
            "line_ids": [
                Command.create({"name": "Order confirmed", "sequence": 1, "days_before_ex_factory": 40}),
                Command.create({"name": "Cutting started", "sequence": 2, "days_before_ex_factory": 20}),
                Command.create({"name": "Goods handed over", "sequence": 3, "days_before_ex_factory": 0}),
            ],
        })

    def make_order(self, qty=None, ex_days=30, confirm=True, **vals):
        """Order on the approved style; ``qty`` {(colour, size): pieces} (default 10 per cell)."""
        order = self.env["garment.order"].create(dict({
            "style_id": self.style.id,
            "ex_factory_date": self.today + timedelta(days=ex_days),
            "date_order": self.today - timedelta(days=60),
            "price_unit": 5.0,
        }, **vals))
        for line in order.line_ids:
            line.qty_ordered = (qty or {}).get((line.colour_id, line.size_id), 0 if qty else 10)
        if confirm:
            order.action_confirm()
        return order
