from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class CuttingCase(TransactionCase):
    """Self-contained data: approved style (S/M/L, two colourways) with two sewing operations,
    a confirmed order, single-size and mixed markers, approved / held rolls in stock."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.today = fields.Date.context_today(env["garment.order"])
        cls.size_range = env["garment.size.range"].create({
            "name": "Cut Test S-L",
            "size_ids": [Command.create({"name": n, "sequence": i * 10}) for i, n in enumerate(["S", "M", "L"])],
        })
        cls.s, cls.m, cls.l = cls.size_range.size_ids.sorted("sequence")
        cls.red = env["garment.colour"].create({"name": "Cut Red", "code": "CRD", "hex": "#AA2233"})
        cls.blue = env["garment.colour"].create({"name": "Cut Blue", "code": "CBL", "hex": "#2233AA"})
        cls.buyer = env["res.partner"].create({"name": "Cut Test Buyer", "is_garment_buyer": True})
        meter = env.ref("uom.product_uom_meter")
        cls.fabric = env["product.product"].create({
            "name": "Cut Test Jersey", "is_storable": True, "tracking": "lot",
            "uom_id": meter.id, "uom_po_id": meter.id})
        cls.op1 = env["garment.operation"].create({"code": "ZCT-01", "name": "Join shoulders", "default_sam": 0.4})
        cls.op2 = env["garment.operation"].create({"code": "ZCT-02", "name": "Attach sleeves", "default_sam": 0.8})
        cls.style = env["garment.style"].create({
            "name": "Cut Test Tee", "code": "ZC-0001", "buyer_id": cls.buyer.id,
            "size_range_id": cls.size_range.id, "colour_ids": [Command.set([cls.red.id, cls.blue.id])],
        })
        cls.techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id,
            "base_size_id": cls.m.id,
            "bom_line_ids": [Command.create({"product_id": cls.fabric.id, "material_kind": "fabric",
                                             "consumption": 1.2, "wastage_pct": 5.0, "price_unit": 2.0})],
            "operation_ids": [Command.create({"operation_id": cls.op1.id, "sequence": 1}),
                              Command.create({"operation_id": cls.op2.id, "sequence": 2})],
        })
        cls.techpack.sudo().action_submit()
        cls.techpack.sudo().action_approve()

        cls.order = env["garment.order"].create({
            "style_id": cls.style.id, "buyer_id": cls.buyer.id,
            "ex_factory_date": cls.today + timedelta(days=30), "date_order": cls.today - timedelta(days=30),
        })
        qty = {cls.s: 100, cls.m: 200, cls.l: 150}
        for line in cls.order.line_ids:
            line.qty_ordered = qty[line.size_id] if line.colour_id == cls.red else 50
        cls.order.action_confirm()

        Marker = env["garment.marker"]
        cls.marker_mix = Marker.create({
            "name": "MIX", "style_id": cls.style.id, "length_m": 4.0, "efficiency_pct": 82.0,
            "line_ids": [Command.create({"size_id": cls.s.id, "ratio": 1}),
                         Command.create({"size_id": cls.m.id, "ratio": 2}),
                         Command.create({"size_id": cls.l.id, "ratio": 1})],
        })
        cls.single = {}
        for size in (cls.s, cls.m, cls.l):
            cls.single[size] = Marker.create({
                "name": "ONE-%s" % size.name, "style_id": cls.style.id, "length_m": 1.1, "efficiency_pct": 75.0,
                "line_ids": [Command.create({"size_id": size.id, "ratio": 1})],
            })

        warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.stock_location = warehouse.lot_stock_id
        cls.roll_a = cls._roll("ZC-R1", "approved", "A", 500.0)
        cls.roll_b = cls._roll("ZC-R2", "approved", "B", 500.0)
        cls.roll_small = cls._roll("ZC-R3", "approved", "A", 10.0)
        cls.roll_hold = cls._roll("ZC-R4", "approved", "A", 500.0)
        cls.roll_hold.action_roll_hold("Shade band")

        cls.cutter = new_test_user(env, "cut_user", groups="zyra_garment_base.group_garment_cutting")
        cls.supervisor = new_test_user(env, "cut_supervisor", groups="zyra_garment_base.group_garment_line_supervisor")
        cls.line = env["mrp.workcenter"].create({"name": "Cut Test Line", "code": "CTL"})
        cls.operator = env["hr.employee"].create({"name": "Cut Test Operator"})

    @classmethod
    def _roll(cls, name, status, shade, metres):
        lot = cls.env["stock.lot"].create({
            "name": name, "product_id": cls.fabric.id, "company_id": cls.env.company.id,
            "is_fabric_roll": True, "roll_status": status, "shade_group": shade})
        cls.env["stock.quant"]._update_available_quantity(cls.fabric, cls.stock_location, metres, lot_id=lot)
        return lot

    def make_plan(self, colour=None, **vals):
        return self.env["garment.cut.plan"].create(dict({
            "order_id": self.order.id, "colour_id": (colour or self.red).id}, **vals))

    def cut_lay(self, lay, rolls=None):
        """Spread ``lay`` on ``rolls`` [(lot, plies)] (default: all planned plies on roll A) and cut it."""
        rolls = rolls or [(self.roll_a, lay.plies_planned)]
        lay.roll_line_ids = [Command.create({"lot_id": lot.id, "plies": plies, "sequence": i})
                             for i, (lot, plies) in enumerate(rolls)]
        lay.action_cut()
        return lay
