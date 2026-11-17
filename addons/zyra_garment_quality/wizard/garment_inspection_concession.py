from odoo import fields, models


class GarmentInspectionConcessionWizard(models.TransientModel):
    _name = "garment.inspection.concession.wizard"
    _description = "Accept a failed lot under concession"

    inspection_id = fields.Many2one("garment.inspection", required=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.inspection_id._garment_accept_concession(self.reason)
        return {"type": "ir.actions.act_window_close"}
