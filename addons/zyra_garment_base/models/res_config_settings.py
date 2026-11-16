from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    garment_currency_id = fields.Many2one(related="company_id.currency_id", string="Garment Currency")
    minute_value = fields.Monetary(
        related="company_id.minute_value", readonly=False, currency_field="garment_currency_id")
    target_efficiency = fields.Float(related="company_id.target_efficiency", readonly=False)
    working_minutes_per_day = fields.Integer(related="company_id.working_minutes_per_day", readonly=False)
    margin_floor_pct = fields.Float(related="company_id.margin_floor_pct", readonly=False)
    garment_week_start = fields.Selection(related="company_id.garment_week_start", readonly=False)
    garment_fabric_accept_points = fields.Float(
        related="company_id.garment_fabric_accept_points", readonly=False)

    def action_open_garment_setup(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "zyra_garment_base.action_garment_setup_wizard")
