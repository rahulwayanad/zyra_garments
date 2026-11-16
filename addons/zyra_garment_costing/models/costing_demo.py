from datetime import date, timedelta

from odoo import Command, api, models

T = "zyra_techpack."
B = "zyra_garment_base."
C = "zyra_garment_costing."

PROCESSES = {
    "tee": [("print", "Chest print, plastisol", B + "partner_vendor_sunrise_prints", "piece", 0.18),
            ("testing", "Fabric and garment lab tests", None, "order", 180.0),
            ("packing", "Folding, tagging and cartons", None, "piece", 0.06)],
    "polo": [("embroidery", "Left chest logo", B + "partner_vendor_sunrise_prints", "piece", 0.22),
             ("testing", "Colour fastness and pilling", None, "order", 220.0),
             ("packing", "Folding, tagging and cartons", None, "piece", 0.07)],
    "chino": [("wash", "Garment enzyme wash", B + "partner_vendor_kaveri_wash", "piece", 0.30),
              ("testing", "Fabric and garment lab tests", None, "order", 240.0),
              ("packing", "Folding, tagging and cartons", None, "piece", 0.08)],
    "jean": [("wash", "Stone wash and tint", B + "partner_vendor_kaveri_wash", "piece", 0.55),
             ("testing", "Shrinkage and seam strength", None, "order", 260.0),
             ("packing", "Folding, tagging and cartons", None, "piece", 0.08)],
    "oxford": [("testing", "Fabric lab tests", None, "order", 150.0),
               ("packing", "Folding, collar insert, cartons", None, "piece", 0.09)],
}


class GarmentCostSheetDemo(models.AbstractModel):
    _name = "garment.cost.sheet.demo"
    _description = "Cost Sheet Demo Loader"

    @api.model
    def _sheet(self, xmlid, key, techpack_xmlid, costing_date, **vals):
        Sheet = self.env["garment.cost.sheet"]
        techpack = self.env.ref(T + techpack_xmlid)
        values = {
            "techpack_id": techpack.id,
            "costing_date": costing_date,
            "user_id": self.env.ref(B + "user_anjali").id,
            "process_line_ids": [
                Command.create({
                    "process_type": ptype, "name": name, "charge_basis": basis, "cost": cost,
                    "partner_id": self.env.ref(partner).id if partner else False,
                }) for ptype, name, partner, basis, cost in PROCESSES[key]
            ],
        }
        values.update(vals)
        sheet = Sheet.create(values)
        self.env["ir.model.data"]._update_xmlids([{"xml_id": C + xmlid, "record": sheet, "noupdate": True}])
        return sheet

    @api.model
    def _load_demo(self):
        if self.env.ref(C + "cost_sheet_tee_v1", raise_if_not_found=False):
            return True
        admin = self.env.ref("base.user_admin")
        # SAM of the demo operation bulletins is small; a realistic cost per minute keeps prices sensible.
        common = {"overhead_pct": 3.0, "commission_pct": 0.0, "cost_per_minute": 0.0573, "line_efficiency": 62.0}

        # Crew neck tee: v1 approved, v2 being reworked (draft)
        tee = self._sheet("cost_sheet_tee_v1", "tee", "techpack_crew_tee_v1", date(2026, 8, 6),
                          quantity_basis=6000, margin_pct=15.0, target_price=5.00, freight_pc=0.12, **common)
        tee.action_submit()
        tee.with_user(admin).action_approve()
        tee_v2 = tee.browse(tee.with_user(admin).action_new_version()["res_id"])
        tee_v2.write({"margin_pct": 14.0, "costing_date": date(2026, 10, 11), "quantity_basis": 7200})
        self.env["ir.model.data"]._update_xmlids([
            {"xml_id": C + "cost_sheet_tee_v2", "record": tee_v2, "noupdate": True}])

        # Classic polo: approved below the margin floor by the Factory Manager, with the reason
        polo = self._sheet("cost_sheet_polo_v1", "polo", "techpack_polo_v1", date(2026, 8, 11),
                           quantity_basis=5230, margin_pct=4.5, target_price=5.40, freight_pc=0.24, **common)
        polo.action_submit()
        polo.with_user(admin).with_context(garment_floor_reason=(
            "Volume order from a strategic buyer; the line would otherwise stand idle in the lean weeks."
        )).action_approve()

        # Chino: v1 on tech pack v1, superseded by v2 on tech pack v2
        chino = self._sheet("cost_sheet_chino_v1", "chino", "techpack_chino_v1", date(2026, 8, 24),
                            quantity_basis=4990, margin_pct=13.0, target_price=9.60, freight_pc=0.30, **common)
        chino.action_submit()
        chino.with_user(admin).action_approve()
        chino_v2 = chino.browse(chino.with_user(admin).action_new_version()["res_id"])
        chino_v2.write({"margin_pct": 14.5, "costing_date": date(2026, 9, 27)})
        chino_v2.action_submit()
        chino_v2.with_user(admin).action_approve()
        self.env["ir.model.data"]._update_xmlids([
            {"xml_id": C + "cost_sheet_chino_v2", "record": chino_v2, "noupdate": True}])

        # Straight leg jean: awaiting approval, under the floor (red)
        jean = self._sheet("cost_sheet_jean_v1", "jean", "techpack_jean_v1", date(2026, 10, 7),
                           quantity_basis=3600, margin_pct=5.5, target_price=7.90, freight_pc=0.32, **common)
        jean.action_submit()

        # Polo for a second buyer: rejected (margin far under the floor)
        polo_b = self._sheet("cost_sheet_polo_bluefin_v1", "polo", "techpack_polo_v1", date(2026, 9, 3),
                             buyer_id=self.env.ref(B + "partner_buyer_bluefin").id,
                             quantity_basis=1750, margin_pct=3.9, target_price=5.30, freight_pc=0.24, **common)
        polo_b.action_submit()
        polo_b.with_user(admin).action_reject()

        # Oxford shirt: tech pack still awaiting approval; sheet in draft
        self._sheet("cost_sheet_oxford_v1", "oxford", "techpack_oxford_v1", date(2026, 10, 10),
                    quantity_basis=2400, margin_pct=15.0, target_price=8.40, sam=14.5, freight_pc=0.26, **common)
        # Approval dates a few days after costing, like a real desk.
        for sheet in self.env["garment.cost.sheet"].search([("approved_date", "!=", False)]):
            sheet.approved_date = sheet.costing_date + timedelta(days=2)
        return True
