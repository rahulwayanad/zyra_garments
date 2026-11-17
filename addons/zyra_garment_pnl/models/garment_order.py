from odoo import fields, models


class GarmentOrder(models.Model):
    _inherit = "garment.order"

    pnl_ids = fields.One2many("garment.order.pnl", "order_id", string="P&L")

    def _garment_pnl(self, refresh=True):
        """P&L record of each order (created when missing); refreshed from the source documents."""
        Pnl = self.env["garment.order.pnl"].sudo()
        result = Pnl
        for order in self:
            pnl = order.sudo().pnl_ids[:1] or Pnl.create({"order_id": order.id})
            if refresh:
                pnl.action_refresh()
            result |= pnl
        return result.with_env(self.env)

    def action_view_pnl(self):
        self.ensure_one()
        pnl = self._garment_pnl()
        return {
            "type": "ir.actions.act_window",
            "res_model": "garment.order.pnl",
            "res_id": pnl.id,
            "view_mode": "form",
        }
