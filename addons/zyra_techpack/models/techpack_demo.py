"""Demo loader: fills the demo tech packs (materials, measurements, construction, operations), approves them and
creates the second revisions. Called once from demo/zyra_techpack_demo.xml. Invented data only."""
from odoo import api, models

B = "zyra_garment_base."
T = "zyra_techpack."

# (product, kind, placement, colour or None, consumption, wastage %)
TEE_BOM = [
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "colour_navy", 1.15, 6.0),
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "colour_white", 1.15, 5.0),
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "colour_black", 1.15, 6.0),
    (T + "product_trim_neck_rib", "trim", "Neck", None, 0.48, 3.0),
    (T + "product_trim_neck_tape", "trim", "Back neck", None, 0.20, 3.0),
    (T + "product_trim_thread", "trim", "All seams", None, 0.03, 0.0),
    (T + "product_trim_main_label", "trim", "Centre back neck", None, 1.0, 0.0),
    (T + "product_trim_care_label", "trim", "Left side seam", None, 1.0, 0.0),
    (T + "product_pack_polybag", "packing", "", None, 1.0, 0.0),
    (T + "product_pack_carton", "packing", "", None, 1.0, 0.0),
]
POLO_BOM = [
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "colour_navy", 1.25, 5.0),
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "colour_black", 1.25, 4.0),
    (T + "product_trim_shirt_button", "trim", "Placket", None, 3.0, 2.0),
    (T + "product_trim_neck_rib", "trim", "Collar, cuffs", None, 0.95, 3.0),
    (T + "product_trim_interlining", "trim", "Placket", None, 0.05, 5.0),
    (T + "product_trim_thread", "trim", "All seams", None, 0.035, 0.0),
    (T + "product_trim_main_label", "trim", "Centre back neck", None, 1.0, 0.0),
    (T + "product_trim_care_label", "trim", "Left side seam", None, 1.0, 0.0),
    (T + "product_pack_polybag", "packing", "", None, 1.0, 0.0),
]
CHINO_BOM = [
    (T + "product_fabric_twill", "fabric", "Body", "colour_black", 1.35, 5.0),
    (T + "product_fabric_twill", "fabric", "Body", "colour_grey", 1.35, 5.0),
    (T + "product_fabric_pocketing", "fabric", "Pocket bags", None, 0.25, 4.0),
    (T + "product_trim_zip", "trim", "Fly", None, 1.0, 1.0),
    (T + "product_trim_shank_button", "trim", "Waistband", None, 1.0, 1.0),
    (T + "product_trim_interlining", "trim", "Waistband", None, 0.10, 5.0),
    (T + "product_trim_thread", "trim", "All seams", None, 0.06, 0.0),
    (T + "product_trim_main_label", "trim", "Back waistband", None, 1.0, 0.0),
    (T + "product_trim_care_label", "trim", "Left side seam", None, 1.0, 0.0),
    (T + "product_trim_hangtag", "trim", "Belt loop", None, 1.0, 0.0),
    (T + "product_pack_polybag", "packing", "", None, 1.0, 0.0),
]
JEAN_BOM = [
    (B + "product_fabric_denim", "fabric", "Body", "colour_indigo", 1.40, 6.0),
    (T + "product_fabric_pocketing", "fabric", "Pocket bags", None, 0.25, 4.0),
    (T + "product_trim_zip", "trim", "Fly", None, 1.0, 1.0),
    (T + "product_trim_shank_button", "trim", "Waistband", None, 1.0, 1.0),
    (T + "product_trim_rivet", "trim", "Front pockets, coin pocket", None, 6.0, 2.0),
    (T + "product_trim_thread", "trim", "All seams", None, 0.08, 0.0),
    (T + "product_trim_main_label", "trim", "Back waistband", None, 1.0, 0.0),
    (T + "product_trim_care_label", "trim", "Left side seam", None, 1.0, 0.0),
    (T + "product_trim_hangtag", "trim", "Belt loop", None, 1.0, 0.0),
    (T + "product_pack_polybag", "packing", "", None, 1.0, 0.0),
]
OXFORD_BOM = [
    (B + "product_fabric_poplin", "fabric", "Body, sleeves, collar", "colour_sky", 1.65, 5.0),
    (B + "product_fabric_poplin", "fabric", "Body, sleeves, collar", "colour_white", 1.65, 5.0),
    (T + "product_trim_shirt_button", "trim", "Front, cuffs, collar points", None, 12.0, 2.0),
    (T + "product_trim_interlining", "trim", "Collar, cuffs", None, 0.15, 5.0),
    (T + "product_trim_thread", "trim", "All seams", None, 0.05, 0.0),
    (T + "product_trim_main_label", "trim", "Centre back yoke", None, 1.0, 0.0),
    (T + "product_pack_polybag", "packing", "", None, 1.0, 0.0),
]

# (pom code, base value, tol +, tol -, grade rule)
TEE_SPEC = [
    ("T04", 70.0, 1.5, 1.5, 2.0), ("T01", 51.0, 1.0, 0.5, 2.5), ("T03", 50.5, 1.0, 1.0, 2.5),
    ("T06", 44.0, 1.0, 1.0, 1.5), ("T11", 20.5, 0.5, 0.5, 0.5), ("T13", 19.0, 0.5, 0.5, 0.75),
    ("T15", 16.5, 0.5, 0.5, 0.5), ("T17", 17.5, 0.5, 0.5, 0.5), ("T18", 8.75, 0.5, 0.5, 0.25),
]
POLO_SPEC = [
    ("T04", 72.0, 1.5, 1.5, 2.0), ("T01", 53.5, 1.0, 0.5, 2.5), ("T03", 53.0, 1.0, 1.0, 2.5),
    ("T06", 45.5, 1.0, 1.0, 1.5), ("T11", 23.2, 0.5, 0.5, 0.5), ("T13", 19.8, 0.5, 0.5, 0.75),
    ("T15", 17.2, 0.5, 0.5, 0.5), ("T17", 18.2, 0.5, 0.5, 0.5), ("T21", 14.0, 0.5, 0.5, 0.0),
]
BOTTOM_SPEC = [
    ("B01", 41.0, 1.0, 1.0, 2.5), ("B02", 52.0, 1.0, 1.0, 2.5), ("B03", 26.5, 0.5, 0.5, 0.6),
    ("B04", 37.0, 0.5, 0.5, 0.8), ("B05", 31.0, 0.5, 0.5, 1.2), ("B06", 21.5, 0.5, 0.5, 0.6),
    ("B07", 18.5, 0.5, 0.5, 0.5), ("B08", 81.0, 1.0, 1.0, 0.0), ("B10", 4.0, 0.2, 0.2, 0.0),
]
SHIRT_SPEC = [
    ("T05", 76.0, 1.0, 1.0, 1.5), ("T01", 56.0, 1.0, 1.0, 2.5), ("T06", 47.0, 0.5, 0.5, 1.5),
    ("T12", 86.0, 1.0, 1.0, 1.5), ("T16", 6.5, 0.2, 0.2, 0.0), ("T20", 4.0, 0.2, 0.2, 0.0),
]

# (area, stitch class, spi, seam type, allowance, note)
KNIT_TOP_CONSTRUCTION = [
    ("Shoulder join", "514", 12, "superimposed", 0.7, "With stay tape"),
    ("Neck attach", "514", 12, "superimposed", 0.6, "Back neck tape, 301 topstitch"),
    ("Armhole", "514", 12, "superimposed", 0.7, ""),
    ("Side seam", "514", 12, "superimposed", 0.7, ""),
    ("Sleeve hem", "406", 12, "edge_finish", 2.0, "Twin needle"),
    ("Bottom hem", "406", 12, "edge_finish", 2.5, "Twin needle"),
    ("Label attach", "301", 10, "lapped", 0.0, "Two sides"),
]
BOTTOM_CONSTRUCTION = [
    ("Seat seam", "401", 10, "flat", 1.0, "Felled, two rows"),
    ("Inseam", "516", 10, "superimposed", 1.0, ""),
    ("Outseam", "516", 10, "superimposed", 1.0, "Single topstitch at pocket"),
    ("Front rise and fly", "301", 10, "lapped", 1.0, "J-stitch, bartack at base"),
    ("Waistband", "401", 10, "bound", 1.0, "Feed-off-the-arm"),
    ("Pockets", "301", 10, "lapped", 0.6, "Double topstitch"),
    ("Leg hem", "301", 10, "edge_finish", 2.0, "Double fold"),
    ("Belt loops", "bartack", 0, "flat", 0.0, "Five loops"),
]
SHIRT_CONSTRUCTION = [
    ("Collar", "301", 14, "superimposed", 1.0, "Fused, edge stitch 1/16\""),
    ("Front placket", "301", 14, "lapped", 1.0, ""),
    ("Yoke", "301", 14, "superimposed", 1.0, "Double yoke"),
    ("Side seam", "401", 12, "flat", 1.0, "Felled"),
    ("Bottom hem", "301", 14, "edge_finish", 0.6, "Narrow hem"),
]


class ZyraTechpackDemo(models.AbstractModel):
    _name = "zyra.techpack.demo"
    _description = "Tech Pack Demo Loader"

    @api.model
    def _ref(self, xmlid):
        return self.env.ref(xmlid if "." in xmlid else B + xmlid)

    @api.model
    def _fill(self, techpack, bom, spec, construction, operations, unit="cm"):
        Pom = self.env["garment.pom"]
        techpack.write({
            "measure_unit": unit,
            "bom_line_ids": [(0, 0, {
                "sequence": index,
                "product_id": self._ref(product).id,
                "material_kind": kind,
                "placement": placement or False,
                "colour_id": self._ref(colour).id if colour else False,
                "consumption": qty,
                "wastage_pct": wastage,
            }) for index, (product, kind, placement, colour, qty, wastage) in enumerate(bom)],
            "measurement_ids": [(0, 0, {
                "sequence": index,
                "pom_id": Pom.search([("code", "=", code)], limit=1).id,
                "base_value": base, "tol_plus": plus, "tol_minus": minus, "grade_rule": grade,
            }) for index, (code, base, plus, minus, grade) in enumerate(spec)],
            "construction_ids": [(0, 0, {
                "sequence": index, "area": area, "stitch_class": stitch, "spi": spi, "seam_type": seam,
                "seam_allowance": allowance, "note": note or False,
            }) for index, (area, stitch, spi, seam, allowance, note) in enumerate(construction)],
            "operation_ids": [(0, 0, {"sequence": index * 10, "operation_id": op.id})
                              for index, op in enumerate(operations, start=1)],
            "label_note": "<p>Woven main label centre back; care label left side seam 8 cm above hem.</p>",
            "packing_note": "<p>Folded to 25 × 35 cm, one piece per polybag, 40 pieces per carton, "
                            "solid colour solid size.</p>",
        })

    @api.model
    def _approve(self, techpack):
        techpack.action_submit()
        techpack.action_approve()

    @api.model
    def _new_revision(self, techpack, xmlid, note):
        action = techpack.action_new_revision()
        new = self.env["zyra.techpack"].browse(action["res_id"])
        new.change_note = note
        self.env["ir.model.data"]._update_xmlids([{"xml_id": T + xmlid, "record": new, "noupdate": True}])
        return new

    @api.model
    def _load_demo(self):
        Operation = self.env["garment.operation"]
        tee_ops = Operation.search([("code", "=like", "TEE-%")], order="sequence, code")
        jean_ops = Operation.search([("code", "=like", "JEAN-%")], order="sequence, code")

        tee = self.env.ref(T + "techpack_crew_tee_v1")
        if tee.bom_line_ids:
            return  # already loaded
        self._fill(tee, TEE_BOM, TEE_SPEC, KNIT_TOP_CONSTRUCTION, tee_ops)
        self._approve(tee)
        tee_v2 = self._new_revision(tee, "techpack_crew_tee_v2", "Body length +1 cm; softer 1x1 neck rib.")
        tee_v2.measurement_ids.filtered(lambda m: m.pom_id.code == "T04").base_value = 71.0

        polo = self.env.ref(T + "techpack_polo_v1")
        self._fill(polo, POLO_BOM, POLO_SPEC, KNIT_TOP_CONSTRUCTION + [
            ("Placket", "301", 11, "lapped", 0.0, "Two-button, fused")], tee_ops)
        self._approve(polo)

        chino = self.env.ref(T + "techpack_chino_v1")
        self._fill(chino, CHINO_BOM, BOTTOM_SPEC, BOTTOM_CONSTRUCTION, jean_ops)
        self._approve(chino)
        chino_v2 = self._new_revision(chino, "techpack_chino_v2", "Buyer fit comments: thigh −0.5 cm, "
                                                                  "fabric wastage 5 % → 4 %.")
        chino_v2.measurement_ids.filtered(lambda m: m.pom_id.code == "B05").base_value = 30.5
        chino_v2.bom_line_ids.filtered(lambda ln: ln.colour_id).wastage_pct = 4.0
        self._approve(chino_v2)

        jean = self.env.ref(T + "techpack_jean_v1")
        self._fill(jean, JEAN_BOM, BOTTOM_SPEC, BOTTOM_CONSTRUCTION, jean_ops)
        self._approve(jean)

        oxford = self.env.ref(T + "techpack_oxford_v1")
        self._fill(oxford, OXFORD_BOM, SHIRT_SPEC, SHIRT_CONSTRUCTION, Operation)
        oxford.action_submit()

        for key in ("crew_tee", "polo", "chino", "jean"):
            style = self.env.ref(T + "style_" + key)
            if style.product_tmpl_id:
                self.env["ir.model.data"]._update_xmlids([{
                    "xml_id": T + "product_tmpl_" + key, "record": style.product_tmpl_id, "noupdate": True}])
        return True
