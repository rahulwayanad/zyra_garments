from odoo import api, fields, models


class GarmentBulletin(models.Model):
    _inherit = "garment.bulletin"

    garment_rate_per_minute = fields.Monetary(string="Rate / Std Minute", compute="_compute_garment_rate_per_minute",
                                              digits=(16, 2))

    @api.depends("total_piece_rate", "total_sam")
    def _compute_garment_rate_per_minute(self):
        for bulletin in self:
            bulletin.garment_rate_per_minute = (bulletin.total_piece_rate / bulletin.total_sam
                                                if bulletin.total_sam else 0.0)
