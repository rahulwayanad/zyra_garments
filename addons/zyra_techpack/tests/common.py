from odoo import Command
from odoo.tests import TransactionCase, new_test_user


class TechpackCase(TransactionCase):
    """Self-contained data: one style (2 colourways × 4 sizes) with a draft tech pack."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.size_range = env["garment.size.range"].create({
            "name": "Test S-XL",
            "size_ids": [Command.create({"name": n, "sequence": i * 10}) for i, n in enumerate(["S", "M", "L", "XL"])],
        })
        cls.s, cls.m, cls.l, cls.xl = cls.size_range.size_ids.sorted("sequence")
        cls.navy = env["garment.colour"].create({"name": "Test Navy", "code": "TNV", "hex": "#1F2A44"})
        cls.white = env["garment.colour"].create({"name": "Test White", "code": "TWH", "hex": "#FFFFFF"})
        cls.buyer = env["res.partner"].create({"name": "Test Buyer Ltd", "is_garment_buyer": True})
        cls.type_tee = env["garment.type"].create({"name": "Test Tee", "code": "TTEE"})
        meter = env.ref("uom.product_uom_meter")
        unit = env.ref("uom.product_uom_unit")
        cls.fabric = env["product.product"].create({
            "name": "Test Jersey", "type": "consu", "is_storable": True,
            "uom_id": meter.id, "uom_po_id": meter.id, "standard_price": 2.0})
        cls.label = env["product.product"].create({
            "name": "Test Label", "type": "consu", "uom_id": unit.id, "uom_po_id": unit.id, "standard_price": 0.05})
        cls.button = env["product.product"].create({
            "name": "Test Button", "type": "consu", "uom_id": unit.id, "uom_po_id": unit.id, "standard_price": 0.10})
        cls.pom_chest = env["garment.pom"].create({"code": "ZT01", "name": "Test chest", "default_tolerance": 1.0})
        cls.pom_length = env["garment.pom"].create({"code": "ZT02", "name": "Test length", "default_tolerance": 1.5})
        cls.op1 = env["garment.operation"].create({"code": "ZOP-1", "name": "Join shoulders", "default_sam": 0.4})
        cls.op2 = env["garment.operation"].create({"code": "ZOP-2", "name": "Side seams", "default_sam": 1.1})

        cls.designer = new_test_user(env, "tp_designer", groups="zyra_garment_base.group_garment_techpack_designer")
        cls.merchandiser = new_test_user(env, "tp_merch", groups="zyra_garment_base.group_garment_merchandiser")
        cls.manager = new_test_user(env, "tp_manager", groups="zyra_garment_base.group_garment_factory_manager")

        cls.style = env["garment.style"].create({
            "name": "Test Crew Tee", "code": "ZT-0001", "buyer_id": cls.buyer.id, "type_id": cls.type_tee.id,
            "size_range_id": cls.size_range.id, "colour_ids": [Command.set([cls.navy.id, cls.white.id])],
        })
        cls.techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id,
            "base_size_id": cls.m.id,
            "bom_line_ids": [
                Command.create({"product_id": cls.fabric.id, "material_kind": "fabric", "colour_id": cls.navy.id,
                                "consumption": 1.2, "wastage_pct": 5.0, "price_unit": 2.0}),
                Command.create({"product_id": cls.fabric.id, "material_kind": "fabric", "colour_id": cls.white.id,
                                "consumption": 1.0, "wastage_pct": 10.0, "price_unit": 2.0}),
                Command.create({"product_id": cls.label.id, "material_kind": "trim", "consumption": 1.0,
                                "price_unit": 0.05}),
                Command.create({"product_id": cls.button.id, "material_kind": "trim", "size_id": cls.xl.id,
                                "consumption": 2.0, "wastage_pct": 50.0, "price_unit": 0.10}),
            ],
            "measurement_ids": [
                Command.create({"pom_id": cls.pom_chest.id, "base_value": 50.0, "grade_rule": 2.5}),
                Command.create({"pom_id": cls.pom_length.id, "base_value": 70.0, "grade_rule": 2.0,
                                "tol_plus": 1.5, "tol_minus": 1.0}),
            ],
            "construction_ids": [
                Command.create({"area": "Side seam", "stitch_class": "514", "spi": 12, "seam_type": "superimposed",
                                "seam_allowance": 0.7}),
            ],
            "operation_ids": [
                Command.create({"operation_id": cls.op1.id, "sequence": 10}),
                Command.create({"operation_id": cls.op2.id, "sequence": 20}),
            ],
        })

    @classmethod
    def approve(cls, techpack):
        techpack.with_user(cls.designer).action_submit()
        techpack.with_user(cls.manager).action_approve()
