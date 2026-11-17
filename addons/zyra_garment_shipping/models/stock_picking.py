from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    garment_shipment_id = fields.Many2one("garment.shipment", string="Garment Shipment", index=True,
                                          copy=False, ondelete="set null")
