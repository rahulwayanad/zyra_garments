from odoo import api, fields, models


class GarmentShipmentOverrideWizard(models.TransientModel):
    _name = "garment.shipment.override.wizard"
    _description = "Shipment Manager Override"

    shipment_id = fields.Many2one("garment.shipment", required=True)
    warnings = fields.Text(compute="_compute_warnings")
    reason = fields.Text(required=True)

    @api.depends("shipment_id")
    def _compute_warnings(self):
        for wiz in self:
            wiz.warnings = "\n".join(wiz.shipment_id._shipping_warnings()) if wiz.shipment_id else False

    def action_override(self):
        self.ensure_one()
        self.shipment_id._garment_override(self.reason)
        return {"type": "ir.actions.act_window_close"}
