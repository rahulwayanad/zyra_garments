import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GarmentColour(models.Model):
    _name = "garment.colour"
    _description = "Garment Colour"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help="Short colour code used in references, e.g. NAVY.")
    pantone = fields.Char(string="Pantone", help="Pantone reference, e.g. 19-4052 TCX.")
    hex = fields.Char(string="Hex", help="Screen colour, e.g. #1F2A44.")
    active = fields.Boolean(default=True)

    @api.constrains("hex")
    def _check_hex(self):
        for colour in self:
            if colour.hex and not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour.hex):
                raise ValidationError(_("Hex colour %(hex)s must look like #1F2A44.", hex=colour.hex))
