from collections import defaultdict

from odoo import _, api, fields, models
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = "sale.order"

    garment_order_ids = fields.One2many("garment.order", "sale_order_id", string="Production Orders")
    garment_order_count = fields.Integer(compute="_compute_garment_order_count")

    @api.depends("garment_order_ids")
    def _compute_garment_order_count(self):
        for so in self:
            so.garment_order_count = len(so.garment_order_ids)

    def action_confirm(self):
        res = super().action_confirm()
        self._create_garment_orders()
        return res

    def _create_garment_orders(self):
        """Rule: confirming a sale order opens one production order per garment style on it,
        with the size × colour grid taken from the variants ordered."""
        Order = self.env["garment.order"]
        created = Order
        template = self.env["garment.tna.template"].search(
            [("company_id", "in", [False, self.env.company.id])], limit=1)
        for so in self:
            by_style = defaultdict(lambda: self.env["sale.order.line"])
            for line in so.order_line:
                style = line.product_id.product_tmpl_id.garment_style_id \
                    if "garment_style_id" in line.product_id.product_tmpl_id._fields else False
                if style and line.product_uom_qty > 0:
                    by_style[style] |= line
            for style, lines in by_style.items():
                if so.garment_order_ids.filtered(lambda o: o.style_id == style and o.state != "cancel"):
                    continue
                qty_by_cell = defaultdict(int)
                amount = 0.0
                for line in lines:
                    colour = line.product_id.garment_colour_id
                    size = line.product_id.garment_size_id
                    if not colour or not size:
                        continue
                    qty_by_cell[(colour, size)] += int(round(line.product_uom_qty))
                    amount += line.price_subtotal
                if not qty_by_cell:
                    continue
                pieces = sum(qty_by_cell.values())
                colours = self.env["garment.colour"].browse(sorted({c.id for c, _s in qty_by_cell}))
                ex_factory = (so.commitment_date or so.expected_date or fields.Datetime.now()).date()
                order_date = so.date_order.date() if so.date_order else fields.Date.context_today(self)
                order = Order.create({
                    "sale_order_id": so.id,
                    "company_id": so.company_id.id,
                    "style_id": style.id,
                    "buyer_id": so.partner_id.commercial_partner_id.id,
                    "buyer_po": so.client_order_ref,
                    "date_order": order_date,
                    "ex_factory_date": max(ex_factory, order_date),
                    "price_unit": amount / pieces if pieces else 0.0,
                    "tna_template_id": template.id,
                    "colour_ids": [Command.set(colours.ids)],
                    "size_ids": [Command.set(style.size_range_id.size_ids.ids)],
                })
                cells = {(l.colour_id, l.size_id): l for l in order.line_ids}
                for key, qty in qty_by_cell.items():
                    if key in cells:
                        cells[key].qty_ordered = qty
                        cells[key].product_id = style._get_variant(*key) if hasattr(style, "_get_variant") \
                            else False
                order.action_confirm()
                order.message_post(body=_("Opened from sale order %s.", so.name))
                created |= order
        return created

    def action_view_garment_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_order")
        action["domain"] = [("sale_order_id", "=", self.id)]
        if len(self.garment_order_ids) == 1:
            action["view_mode"] = "form"
            action["views"] = [(False, "form")]
            action["res_id"] = self.garment_order_ids.id
        return action
