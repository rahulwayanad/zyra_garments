from odoo import fields, models


class GarmentScan(models.Model):
    _inherit = "garment.scan"

    wage_line_id = fields.Many2one("garment.wage.sheet.line", string="Wage Sheet Line", index=True,
                                   copy=False, ondelete="set null", readonly=True)
