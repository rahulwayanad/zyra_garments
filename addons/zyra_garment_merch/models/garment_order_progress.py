from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GarmentOrderProgress(models.Model):
    """One posting of cut / sewn / packed / shipped pieces against a grid cell.

    Created only through ``garment.order._garment_add_progress``; never edited afterwards
    (post a negative quantity to correct).
    """

    _name = "garment.order.progress"
    _description = "Production Order Progress Posting"
    _order = "date desc, id desc"

    order_id = fields.Many2one("garment.order", required=True, ondelete="cascade", index=True)
    line_id = fields.Many2one("garment.order.line", string="Grid Cell", required=True, ondelete="cascade",
                              index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    colour_id = fields.Many2one(related="line_id.colour_id", store=True, string="Colourway")
    size_id = fields.Many2one(related="line_id.size_id", store=True, string="Size")
    stage = fields.Selection([
        ("cut", "Cut"),
        ("sewn", "Sewn"),
        ("packed", "Packed"),
        ("shipped", "Shipped"),
    ], required=True, index=True)
    qty = fields.Integer(string="Pieces", required=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    user_id = fields.Many2one("res.users", string="Posted By", default=lambda self: self.env.user)
    ref = fields.Char(string="Reference", help="Bundle, lay, carton or shipment that produced the posting.")

    @api.depends("order_id.name", "stage", "qty")
    def _compute_display_name(self):
        labels = dict(self._fields["stage"]._description_selection(self.env))
        for rec in self:
            rec.display_name = "%s · %s %+d" % (rec.order_id.name or "", labels.get(rec.stage, ""), rec.qty)

    def write(self, vals):
        raise UserError(_("Production postings cannot be changed; post a correction instead."))
