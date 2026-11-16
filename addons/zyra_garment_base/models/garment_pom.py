from odoo import api, fields, models


class GarmentPom(models.Model):
    _name = "garment.pom"
    _description = "Point of Measure"
    _order = "sequence, code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    garment_category = fields.Selection(
        [("top", "Tops"), ("bottom", "Bottoms"), ("both", "All garments")],
        string="Used On", default="both", required=True)
    how_to_measure = fields.Text(string="How to Measure", translate=True)
    default_tolerance = fields.Float(
        string="Default Tolerance (+/- cm)", digits=(16, 2), default=1.0,
        help="Allowed difference either side of the spec value, in centimetres.")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Point of measure codes must be unique."),
        ("tolerance_positive", "CHECK(default_tolerance >= 0)", "Tolerance cannot be negative."),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for pom in self:
            pom.display_name = f"[{pom.code}] {pom.name}" if pom.code else pom.name
