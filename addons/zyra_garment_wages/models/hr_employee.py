from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    garment_paid_by = fields.Selection([("piece", "Piece rate"), ("time", "Time rate")], string="Paid By",
                                       default="piece", groups="hr.group_hr_user,zyra_garment_base.group_garment_wages",
                                       help="Piece rate: earnings from scans, topped up to the minimum. "
                                            "Time rate: paid the minimum for the days attended, no incentive.")
