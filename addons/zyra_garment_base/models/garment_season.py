from odoo import fields, models


class GarmentSeason(models.Model):
    _name = "garment.season"
    _description = "Garment Season"
    _order = "year desc, code"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="Short code, e.g. SS27.")
    year = fields.Integer(required=True, default=lambda self: fields.Date.today().year)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Season codes must be unique."),
    ]
