from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    garment_pnl_order_id = fields.Many2one(
        "garment.order", string="Charged to Order", index="btree_not_null",
        help="Material (e.g. trims) issued to this production order; its stock value is a material cost "
             "in the order P&L. Fabric cut on a lay is charged through the lay.")
