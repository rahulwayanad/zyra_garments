from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class GarmentOrderLine(models.Model):
    """One cell of the size × colour grid of a production order."""

    _name = "garment.order.line"
    _description = "Production Order Grid Cell"
    _order = "order_id, sequence, id"

    order_id = fields.Many2one("garment.order", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    sequence = fields.Integer(default=10)
    colour_id = fields.Many2one("garment.colour", string="Colourway", required=True, index=True)
    colour_hex = fields.Char(related="colour_id.hex")
    size_id = fields.Many2one("garment.size", string="Size", required=True, index=True)
    size_sequence = fields.Integer(related="size_id.sequence", string="Size Sequence")
    product_id = fields.Many2one("product.product", string="Variant",
                                 help="Garment variant (colour × size) when the style has a product.")
    qty_ordered = fields.Integer(string="Ordered", default=0)
    progress_ids = fields.One2many("garment.order.progress", "line_id", string="Postings")
    qty_cut = fields.Integer(string="Cut", compute="_compute_progress", store=True)
    qty_sewn = fields.Integer(string="Sewn", compute="_compute_progress", store=True)
    qty_packed = fields.Integer(string="Packed", compute="_compute_progress", store=True)
    qty_shipped = fields.Integer(string="Shipped", compute="_compute_progress", store=True)
    qty_balance = fields.Integer(string="Balance", compute="_compute_progress", store=True,
                                 help="Ordered minus shipped.")

    _sql_constraints = [
        ("cell_uniq", "unique(order_id, colour_id, size_id)",
         "A colourway and size appear only once in the grid of an order."),
        ("qty_ordered_positive", "CHECK(qty_ordered >= 0)", "Ordered quantity cannot be negative."),
    ]

    @api.depends("colour_id.name", "size_id.name")
    def _compute_display_name(self):
        for line in self:
            line.display_name = "%s / %s" % (line.colour_id.name or "", line.size_id.name or "")

    @api.depends("progress_ids.qty", "progress_ids.stage", "qty_ordered")
    def _compute_progress(self):
        for line in self:
            totals = dict.fromkeys(("cut", "sewn", "packed", "shipped"), 0)
            for p in line.progress_ids:
                totals[p.stage] += p.qty
            line.qty_cut = totals["cut"]
            line.qty_sewn = totals["sewn"]
            line.qty_packed = totals["packed"]
            line.qty_shipped = totals["shipped"]
            line.qty_balance = line.qty_ordered - totals["shipped"]

    @api.constrains("colour_id", "size_id", "order_id")
    def _check_cell_in_style(self):
        for line in self:
            style = line.order_id.style_id
            if style.size_range_id and line.size_id.range_id != style.size_range_id:
                raise ValidationError(_("Size %(size)s is not in the size range of style %(style)s.",
                                        size=line.size_id.name, style=style.display_name))

    def write(self, vals):
        if "qty_ordered" in vals or "colour_id" in vals or "size_id" in vals:
            for line in self:
                order = line.order_id
                if order.state != "draft" and not order.is_amending:
                    raise UserError(_("Order %s is confirmed: use Amend Order to change the grid.", order.name))
        return super().write(vals)

    def unlink(self):
        if self.progress_ids:
            raise UserError(_("A grid cell with production postings cannot be removed."))
        return super().unlink()
