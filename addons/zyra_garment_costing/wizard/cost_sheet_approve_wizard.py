from odoo import _, fields, models
from odoo.exceptions import UserError


class GarmentCostSheetApproveWizard(models.TransientModel):
    _name = "garment.cost.sheet.approve.wizard"
    _description = "Approve a Cost Sheet below the Margin Floor"

    sheet_id = fields.Many2one("garment.cost.sheet", required=True, readonly=True)
    currency_id = fields.Many2one(related="sheet_id.currency_id")
    margin_pct = fields.Float(related="sheet_id.margin_pct", string="Margin %")
    margin_floor_pct = fields.Float(related="sheet_id.margin_floor_pct", string="Margin Floor %")
    fob_price = fields.Monetary(related="sheet_id.fob_price")
    reason = fields.Text(string="Reason", required=True,
                         help="Kept in the cost sheet history (chatter).")

    def action_confirm(self):
        self.ensure_one()
        if not (self.reason or "").strip():
            raise UserError(_("Give the reason for approving below the margin floor."))
        self.sheet_id._do_approve(reason=self.reason)
        return {"type": "ir.actions.act_window_close"}
