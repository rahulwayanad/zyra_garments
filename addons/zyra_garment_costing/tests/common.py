from odoo import Command
from odoo.tests import TransactionCase, new_test_user


class CostingCase(TransactionCase):
    """A style with two colourways, an approved tech pack (fabric per colourway, one trim, 2 operations)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.write({"minute_value": 0.10, "target_efficiency": 65.0, "margin_floor_pct": 12.0})
        cls.buyer = env["res.partner"].create({"name": "Test Buyer Ltd", "is_garment_buyer": True})
        cls.navy = env["garment.colour"].create({"name": "Test Navy", "code": "TNV", "hex": "#1f2a44"})
        cls.white = env["garment.colour"].create({"name": "Test White", "code": "TWH", "hex": "#ffffff"})
        cls.size_range = env["garment.size.range"].create({
            "name": "Test S-L",
            "size_ids": [Command.create({"name": n, "sequence": i}) for i, n in enumerate(["S", "M", "L"])],
        })
        cls.small, cls.medium, cls.large = cls.size_range.size_ids.sorted("sequence")
        kg = env.ref("uom.product_uom_kgm")
        units = env.ref("uom.product_uom_unit")
        cls.fabric_navy = env["product.product"].create({
            "name": "Test Jersey Navy", "default_code": "T-JER-NV", "uom_id": kg.id, "uom_po_id": kg.id,
            "standard_price": 6.0,
        })
        cls.fabric_white = env["product.product"].create({
            "name": "Test Jersey White", "default_code": "T-JER-WH", "uom_id": kg.id, "uom_po_id": kg.id,
            "standard_price": 5.0,
        })
        cls.label = env["product.product"].create({
            "name": "Test Main Label", "default_code": "T-LBL", "uom_id": units.id, "uom_po_id": units.id,
            "standard_price": 0.04,
        })
        cls.style = env["garment.style"].create({
            "name": "Test Crew Tee", "code": "TST-001", "buyer_id": cls.buyer.id,
            "size_range_id": cls.size_range.id,
            "colour_ids": [Command.set([cls.navy.id, cls.white.id])],
        })
        op1 = env.ref("zyra_garment_base.operation_tee_01")
        op2 = env.ref("zyra_garment_base.operation_tee_02")
        cls.techpack = env["zyra.techpack"].create({
            "style_id": cls.style.id,
            "bom_line_ids": [
                # navy fabric differs by size: S 0.20 / L 0.30 -> averaged 0.25
                Command.create({"product_id": cls.fabric_navy.id, "material_kind": "fabric",
                                "colour_id": cls.navy.id, "size_id": cls.small.id, "consumption": 0.20,
                                "uom_id": kg.id, "wastage_pct": 4.0, "price_unit": 6.0}),
                Command.create({"product_id": cls.fabric_navy.id, "material_kind": "fabric",
                                "colour_id": cls.navy.id, "size_id": cls.large.id, "consumption": 0.30,
                                "uom_id": kg.id, "wastage_pct": 4.0, "price_unit": 6.0}),
                Command.create({"product_id": cls.fabric_white.id, "material_kind": "fabric",
                                "colour_id": cls.white.id, "consumption": 0.25, "uom_id": kg.id,
                                "wastage_pct": 2.0, "price_unit": 5.0}),
                Command.create({"product_id": cls.label.id, "material_kind": "trim",
                                "consumption": 1.0, "uom_id": units.id, "price_unit": 0.04}),
            ],
            "operation_ids": [
                Command.create({"operation_id": op1.id, "sam": 2.5}),
                Command.create({"operation_id": op2.id, "sam": 1.5}),
            ],
        })
        cls.techpack.sudo().write({"state": "approved"})

        cls.costing_user = new_test_user(
            env, login="test_costing", name="Test Costing",
            groups="base.group_user,zyra_garment_base.group_garment_costing")
        cls.merch_user = new_test_user(
            env, login="test_merch", name="Test Merchandiser",
            groups="base.group_user,sales_team.group_sale_salesman,zyra_garment_base.group_garment_merchandiser")
        cls.manager = new_test_user(
            env, login="test_fm", name="Test Factory Manager",
            groups="base.group_user,zyra_garment_base.group_garment_factory_manager")
        cls.Sheet = env["garment.cost.sheet"]

    def _sheet(self, **vals):
        values = {
            "techpack_id": self.techpack.id, "quantity_basis": 1000, "overhead_pct": 3.0,
            "commission_pct": 0.0, "margin_pct": 15.0, "target_price": 4.0,
        }
        values.update(vals)
        return self.Sheet.with_user(self.merch_user).create(values)
