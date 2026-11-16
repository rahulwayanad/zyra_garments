from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    techpack_id = fields.Many2one("zyra.techpack", string="Tech Pack", index=True, copy=False, readonly=True)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    garment_style_id = fields.Many2one(related="product_id.product_tmpl_id.garment_style_id", store=True,
                                       string="Garment Style")
    techpack_id = fields.Many2one(
        "zyra.techpack", string="Tech Pack", index=True, copy=False,
        compute="_compute_techpack_id", store=True, readonly=False, precompute=True,
        domain="[('style_id', '=', garment_style_id)]",
        help="The tech pack revision this order is made to (from the sale order, or the style's current one).")

    @api.depends("product_id")
    def _compute_techpack_id(self):
        for production in self:
            style = production.product_id.product_tmpl_id.garment_style_id
            if not style:
                production.techpack_id = False
            elif production.techpack_id.style_id != style:
                production.techpack_id = style.current_techpack_id

    def _check_techpack_gate(self):
        """An MO for a garment style can be confirmed only when the style's tech pack is approved."""
        for production in self:
            style = production.product_id.product_tmpl_id.garment_style_id
            if not style:
                continue
            if not style.approved_for_production:
                raise UserError(_(
                    "%(mo)s cannot be confirmed: the tech pack of style %(style)s is not approved yet.",
                    mo=production.name, style=style.display_name))
            if not production.techpack_id:
                production.techpack_id = style.current_techpack_id
            elif production.techpack_id.state != "approved":
                raise UserError(_(
                    "%(mo)s is linked to tech pack %(tp)s, which is %(state)s. Link it to %(current)s.",
                    mo=production.name, tp=production.techpack_id.name,
                    state=dict(production.techpack_id._fields["state"].selection)[production.techpack_id.state],
                    current=style.current_techpack_id.name))

    def action_confirm(self):
        self._check_techpack_gate()
        return super().action_confirm()
