from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    garment_style_id = fields.Many2one(related="product_id.product_tmpl_id.garment_style_id", store=True,
                                       string="Garment Style")
    techpack_id = fields.Many2one("zyra.techpack", string="Tech Pack", index=True, copy=False, readonly=True,
                                  help="Tech pack revision in force when the order was confirmed.")

    def _check_techpack_gate(self):
        """A sale order line for a garment style can be confirmed only when its tech pack is approved."""
        blocked = self.filtered(lambda ln: ln.garment_style_id and not ln.garment_style_id.approved_for_production)
        if blocked:
            raise UserError(_(
                "These styles have no approved tech pack, so the order cannot be confirmed: %s",
                ", ".join(blocked.garment_style_id.mapped("display_name"))))
        for line in self.filtered("garment_style_id"):
            line.techpack_id = line.garment_style_id.current_techpack_id

    def _prepare_procurement_values(self, group_id=False):
        values = super()._prepare_procurement_values(group_id=group_id)
        if self.techpack_id:
            values["techpack_id"] = self.techpack_id.id
        return values


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        self.order_line._check_techpack_gate()
        return super().action_confirm()
