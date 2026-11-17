from odoo import api, models


class GarmentOrderPnlDemo(models.Model):
    _inherit = "garment.order.pnl"

    @api.model
    def _load_demo(self):
        return True
