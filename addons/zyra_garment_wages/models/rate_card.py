from odoo import api, fields, models
from odoo.exceptions import UserError


class GarmentRateCard(models.Model):
    _name = "garment.rate.card"
    _description = "Wage Rate Card"
    _inherit = ["mail.thread"]
    _order = "valid_from desc, id desc"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Reference", default="New", readonly=True, copy=False)
    active = fields.Boolean(default=True)
    state = fields.Selection([("draft", "Draft"), ("active", "Active")], default="draft", required=True,
                             tracking=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    basis = fields.Selection([("sam", "Standard minute value")], default="sam", required=True)
    minute_value = fields.Monetary(string="Value of a Standard Minute", required=True, tracking=True,
                                   help="Money paid per earned (standard) minute.")
    hourly_full = fields.Monetary(string="Earnings per Hour at 100% Efficiency", compute="_compute_figures")
    hours_per_day = fields.Float(string="Hours per Day", default=8.0, required=True)
    min_daily_wage = fields.Monetary(string="Guaranteed Daily Minimum", required=True, tracking=True)
    topup_period = fields.Selection([("daily", "Daily"), ("weekly", "Weekly")], string="Top-up to Minimum",
                                    default="weekly", required=True)
    overtime_multiplier = fields.Float(string="Overtime Rate", default=2.0,
                                       help="Times the hourly minimum (daily minimum ÷ hours per day).")
    incentive_threshold = fields.Float(string="Incentive above Efficiency %", default=80.0)
    incentive_percent = fields.Float(string="Incentive % of Piece Earnings", default=10.0)
    valid_from = fields.Date(default=fields.Date.context_today)
    bulletin_ids = fields.Many2many("garment.bulletin", string="Priced Bulletins")
    bulletin_count = fields.Integer(string="Bulletins Priced", compute="_compute_figures")

    @api.depends("minute_value", "bulletin_ids")
    def _compute_figures(self):
        for card in self:
            card.hourly_full = card.minute_value * 60
            card.bulletin_count = len(card.bulletin_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code", "New") == "New":
                vals["code"] = self.env["ir.sequence"].next_by_code("garment.rate.card") or "New"
        return super().create(vals_list)

    def action_activate(self):
        self.write({"state": "active"})
        return True

    def action_apply_to_bulletins(self):
        """Price every operation of the card's bulletins: piece rate = SAM × value of a standard minute.
        Lines whose rate was typed by hand keep it."""
        for card in self:
            if card.state != "active":
                raise UserError(self.env._("Activate the rate card before applying it."))
            if not card.bulletin_ids:
                raise UserError(self.env._("Add the bulletins this card prices first."))
            for line in card.bulletin_ids.line_ids.filtered(lambda l: not l.manual_rate):
                line.piece_rate = round(line.sam * card.minute_value, 4)
            card.bulletin_ids.write({"rate_card": card.name,
                                     "rates_applied_on": fields.Date.context_today(card)})
            card.message_post(body=self.env._("Rates applied to %s bulletins.", len(card.bulletin_ids)))
        return True
