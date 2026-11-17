from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GarmentLcAmendWizard(models.TransientModel):
    _name = "garment.lc.amend.wizard"
    _description = "Amend Letter of Credit"

    lc_id = fields.Many2one("garment.lc", required=True)
    currency_id = fields.Many2one(related="lc_id.currency_id")
    amount = fields.Monetary(string="Amount")
    tolerance_pct = fields.Float(string="Tolerance (%)")
    latest_shipment_date = fields.Date(string="Latest Shipment Date")
    expiry_date = fields.Date(string="Expiry")
    reason = fields.Char(string="Amendment", required=True, help="What the bank amended and why.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        lc = self.env["garment.lc"].browse(res.get("lc_id") or self.env.context.get("default_lc_id"))
        if lc:
            res.update(amount=lc.amount, tolerance_pct=lc.tolerance_pct,
                       latest_shipment_date=lc.latest_shipment_date, expiry_date=lc.expiry_date)
        return res

    def action_amend(self):
        self.ensure_one()
        lc = self.lc_id
        if lc.state == "closed":
            raise UserError(_("A closed credit cannot be amended."))
        vals = {k: self[k] for k in ("amount", "tolerance_pct", "latest_shipment_date", "expiry_date")
                if self[k] != lc[k]}
        if not vals:
            raise UserError(_("Nothing changes in this amendment."))
        vals["amendment_count"] = lc.amendment_count + 1
        lc.write(vals)
        lc.message_post(body=_("Amendment %(n)s: %(reason)s", n=lc.amendment_count, reason=self.reason))
        return {"type": "ir.actions.act_window_close"}
