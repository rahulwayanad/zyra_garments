from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_garment_buyer = fields.Boolean(string="Garment Buyer", help="Places garment orders with us.")
    is_jobwork_vendor = fields.Boolean(
        string="Job-work Vendor", help="Does outsourced print, embroidery, wash or sewing for us.")
    buyer_code = fields.Char(string="Buyer Code", help="Short code used on styles and order references.")

    _sql_constraints = [
        ("buyer_code_unique", "unique(buyer_code)", "Each buyer code can be used by one partner only."),
    ]
