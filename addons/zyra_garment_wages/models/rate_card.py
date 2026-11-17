from odoo import api, fields, models


class GarmentRateCard(models.Model):
    _name = "garment.rate.card"
    _description = "Wage Rate Card"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    minute_value = fields.Float(string="Minute Value", digits=(16, 4), required=True,
                                help="Money paid per earned (standard) minute.")
    hourly_full = fields.Monetary(string="Hourly Earnings @100%", compute="_compute_hourly_full")
    hours_per_day = fields.Float(string="Hours / Day", default=8.0)
    min_daily_wage = fields.Monetary(string="Statutory Minimum / Day", required=True)
    overtime_multiplier = fields.Float(string="Overtime Multiplier", default=2.0,
                                       help="Overtime hour = (minimum per day ÷ hours per day) × multiplier.")
    incentive_threshold = fields.Float(string="Incentive Above Efficiency %", default=80.0)
    incentive_percent = fields.Float(string="Incentive % of Piece Earnings", default=10.0)
    bulletin_ids = fields.Many2many("garment.bulletin", string="Bulletins Priced")
    bulletin_count = fields.Integer(compute="_compute_hourly_full")

    @api.depends("minute_value", "bulletin_ids")
    def _compute_hourly_full(self):
        for card in self:
            card.hourly_full = card.minute_value * 60
            card.bulletin_count = len(card.bulletin_ids)
