from odoo import _, fields, models
from odoo.exceptions import UserError


class GarmentBundleIssue(models.TransientModel):
    _name = "garment.bundle.issue"
    _description = "Issue Bundles to Line"

    bundle_ids = fields.Many2many("garment.bundle", string="Bundles", domain="[('stage', '=', 'cut')]")
    line_id = fields.Many2one("mrp.workcenter", string="Sewing Line", required=True)
    issue_date = fields.Datetime(default=fields.Datetime.now, required=True)

    def action_issue(self):
        self.ensure_one()
        bundles = self.bundle_ids.filtered(lambda b: b.stage == "cut")
        if not bundles:
            raise UserError(_("Choose bundles that are cut and not issued yet."))
        bundles.action_issue(self.line_id, self.issue_date)
        return {"type": "ir.actions.act_window_close"}


class GarmentBundleSplit(models.TransientModel):
    _name = "garment.bundle.split"
    _description = "Split Bundle"

    bundle_id = fields.Many2one("garment.bundle", required=True)
    pieces = fields.Integer(related="bundle_id.pieces")
    pieces_new = fields.Integer(string="Pieces for the New Bundle", required=True)

    def action_split(self):
        self.ensure_one()
        new = self.bundle_id._split(self.pieces_new)
        return {"type": "ir.actions.act_window", "res_model": "garment.bundle", "res_id": new.id,
                "view_mode": "form", "target": "current"}


class GarmentLayEndBits(models.TransientModel):
    _name = "garment.lay.end.bits"
    _description = "Return End Bits"

    lay_id = fields.Many2one("garment.lay", required=True)
    end_bits_m = fields.Float(string="End Bits Returned (m)", digits=(16, 2))
    note = fields.Char()

    def action_confirm(self):
        self.ensure_one()
        if self.end_bits_m < 0:
            raise UserError(_("End bits cannot be negative."))
        self.lay_id.end_bits_m = self.end_bits_m
        self.lay_id.message_post(body=_("End bits returned to the store: %(m).2f m. %(note)s",
                                        m=self.end_bits_m, note=self.note or ""))
        return {"type": "ir.actions.act_window_close"}
