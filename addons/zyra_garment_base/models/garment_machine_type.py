from odoo import fields, models


class GarmentMachineType(models.Model):
    _name = "garment.machine.type"
    _description = "Sewing Machine Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    stitch_class = fields.Char(help="ISO 4915 stitch class the machine makes, e.g. 301, 504.")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Machine type codes must be unique."),
    ]
