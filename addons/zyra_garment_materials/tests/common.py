from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class MaterialsCase(TransactionCase):
    """Own data: approved style with 2 colourways × 2 sizes, a lot-tracked fabric (metres) per colourway and an
    all-colourway trim; a confirmed production order of 100 pieces per cell."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.today = fields.Date.context_today(env["garment.order"])
        cls.company = env.company
        cls.company.garment_fabric_accept_points = 40.0
        metre = env.ref("uom.product_uom_meter")
        unit = env.ref("uom.product_uom_unit")
        cls.vendor = env["res.partner"].create({"name": "Mat Test Mill"})
        cls.buyer = env["res.partner"].create({"name": "Mat Test Buyer", "is_garment_buyer": True})
        cls.size_range = env["garment.size.range"].create({
            "name": "Mat Test S-M",
            "size_ids": [Command.create({"name": n, "sequence": i}) for i, n in enumerate(["S", "M"])],
        })
        cls.s, cls.m = cls.size_range.size_ids.sorted("sequence")
        cls.red = env["garment.colour"].create({"name": "Mat Red", "code": "MTR", "hex": "#AA2233"})
        cls.blue = env["garment.colour"].create({"name": "Mat Blue", "code": "MTB", "hex": "#2233AA"})

        def product(name, uom, tracking, price):
            return env["product.product"].create({
                "name": name, "type": "consu", "is_storable": True, "tracking": tracking,
                "uom_id": uom.id, "uom_po_id": uom.id, "standard_price": price,
                "seller_ids": [Command.create({"partner_id": cls.vendor.id, "price": price})],
            })
        cls.fabric = product("Mat Test Jersey", metre, "lot", 2.0)
        cls.trim = product("Mat Test Label", unit, "none", 0.1)
        cls.style = env["garment.style"].create({
            "name": "Mat Test Tee", "code": "MT-0001", "buyer_id": cls.buyer.id,
            "size_range_id": cls.size_range.id, "colour_ids": [Command.set([cls.red.id, cls.blue.id])],
        })
        cls.techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id,
            "base_size_id": cls.m.id,
            "bom_line_ids": [
                Command.create({"product_id": cls.fabric.id, "material_kind": "fabric", "colour_id": cls.red.id,
                                "consumption": 1.2, "wastage_pct": 5.0, "uom_id": metre.id, "price_unit": 2.0}),
                Command.create({"product_id": cls.fabric.id, "material_kind": "fabric", "colour_id": cls.blue.id,
                                "consumption": 1.2, "wastage_pct": 5.0, "uom_id": metre.id, "price_unit": 2.0}),
                Command.create({"product_id": cls.trim.id, "material_kind": "trim", "consumption": 2.0,
                                "wastage_pct": 0.0, "uom_id": unit.id, "price_unit": 0.1}),
            ],
        })
        cls.techpack.sudo().action_submit()
        cls.techpack.sudo().action_approve()
        cls.store = new_test_user(env, "mat_store", groups="zyra_garment_base.group_garment_fabric_store")
        cls.manager = new_test_user(env, "mat_manager", groups="zyra_garment_base.group_garment_factory_manager")
        cls.order = env["garment.order"].create({
            "style_id": cls.style.id,
            "buyer_id": cls.buyer.id,
            "ex_factory_date": cls.today + timedelta(days=60),
            "date_order": cls.today - timedelta(days=10),
            "price_unit": 5.0,
        })
        for line in cls.order.line_ids:
            line.qty_ordered = 100
        cls.order.action_confirm()
        cls.warehouse = env["stock.warehouse"].search([("company_id", "=", cls.company.id)], limit=1)

    def make_roll(self, name, qty=100.0, booking_line=None, width_cm=152.4, status="received"):
        lot = self.env["stock.lot"].create({
            "name": name, "product_id": self.fabric.id, "company_id": self.company.id, "is_fabric_roll": True,
            "width_cm": width_cm, "roll_received_qty": qty,
            "booking_line_id": booking_line.id if booking_line else False,
        })
        self.env["stock.quant"]._update_available_quantity(self.fabric, self.warehouse.lot_stock_id, qty, lot_id=lot)
        if status != "received":
            lot.roll_status = status
        return lot
