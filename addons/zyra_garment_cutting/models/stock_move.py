from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    garment_lay_id = fields.Many2one("garment.lay", string="Lay", index="btree_not_null", readonly=True,
                                     help="Lay whose cut consumed this fabric.")
