from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    garment_order_id = fields.Many2one("garment.order", string="Production Order", index="btree_not_null",
                                       help="Order this invoice line belongs to (counted as revenue in its P&L).")
