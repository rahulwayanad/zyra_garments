from odoo import fields, models


class GarmentDefect(models.Model):
    _inherit = "garment.defect"

    endline_button = fields.Boolean(string="On the end-line tablet",
                                    help="Show this defect as a button on the end-line check tablet.")
    endline_label = fields.Char(string="Tablet label", help="Short label for the tablet button.")
    endline_sequence = fields.Integer(string="Tablet order", default=10)
