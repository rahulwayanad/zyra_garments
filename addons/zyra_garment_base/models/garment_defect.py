from odoo import api, fields, models

DEFECT_AREAS = [
    ("fabric", "Fabric"),
    ("stitching", "Stitching"),
    ("seam", "Seam"),
    ("measurement", "Measurement"),
    ("shade", "Shade"),
    ("trims", "Trims & Accessories"),
    ("print", "Print / Embroidery"),
    ("wash", "Wash"),
    ("finishing", "Finishing / Pressing"),
    ("packing", "Packing & Labelling"),
]

DEPARTMENTS = [
    ("fabric_store", "Fabric Store"),
    ("cutting", "Cutting"),
    ("sewing", "Sewing"),
    ("jobwork", "Job Work"),
    ("finishing", "Finishing"),
    ("packing", "Packing"),
]


class GarmentDefect(models.Model):
    _name = "garment.defect"
    _description = "Garment Defect"
    _order = "sequence, code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    area = fields.Selection(DEFECT_AREAS, required=True, default="stitching",
                            help="Kind of defect (what is wrong), not the place on the garment.")
    severity = fields.Selection(
        [("minor", "Minor"), ("major", "Major"), ("critical", "Critical")],
        required=True, default="major")
    department = fields.Selection(DEPARTMENTS, required=True, default="sewing",
                                  help="Department where this defect is usually caused.")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Defect codes must be unique."),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for defect in self:
            defect.display_name = f"[{defect.code}] {defect.name}" if defect.code else defect.name
