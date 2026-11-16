from odoo import fields, models


class GarmentType(models.Model):
    _name = "garment.type"
    _description = "Garment Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    default_sam = fields.Float(string="Default SAM", digits=(16, 2),
                               help="Standard allowed minutes for a typical garment of this type.")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Garment type codes must be unique."),
        ("default_sam_positive", "CHECK(default_sam >= 0)", "Default SAM cannot be negative."),
    ]
