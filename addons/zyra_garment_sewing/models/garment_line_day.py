from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class GarmentLineDay(models.Model):
    """Daily line summary (screen 58): one record per line and day, filled from the scans
    (:meth:`garment.line._garment_daily_summary` / ``_garment_hourly_board``) and closed by the supervisor."""
    _name = "garment.line.day"
    _inherit = ["mail.thread"]
    _description = "Line Day"
    _order = "date desc, id desc"

    name = fields.Char(default="/", readonly=True, copy=False)
    line_id = fields.Many2one("garment.line", string="Sewing Line", required=True, index=True)
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    state = fields.Selection([("open", "Open"), ("closed", "Closed")], default="open", required=True,
                             tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    supervisor_id = fields.Many2one(related="line_id.supervisor_id")
    order_id = fields.Many2one("garment.order", string="Order")
    bulletin_id = fields.Many2one("garment.bulletin", string="Bulletin")
    working_minutes = fields.Integer()
    available_minutes = fields.Integer()
    earned_minutes = fields.Float(digits=(16, 1))
    planned_efficiency = fields.Float(string="Planned Efficiency", digits=(16, 0))
    operators = fields.Integer()
    pieces = fields.Integer(string="Pieces off Line")
    target = fields.Integer()
    efficiency = fields.Float(digits=(16, 0))
    lost_minutes = fields.Float(digits=(16, 0))
    wip_days = fields.Float(string="WIP Days", digits=(16, 1))
    dhu = fields.Float(string="DHU", digits=(16, 1))
    hour_ids = fields.One2many("garment.line.day.hour", "day_id", string="Hours")
    downtime_ids = fields.One2many("garment.line.day.downtime", "day_id", string="Downtime")
    title = fields.Char(compute="_compute_title")

    _sql_constraints = [("line_day_unique", "UNIQUE(line_id, date)", "One summary per line and day.")]

    @api.depends("line_id", "date")
    def _compute_title(self):
        for day in self:
            day.title = " · ".join(filter(None, [day.line_id.name,
                                                 day.date and day.date.strftime("%A %d %b")]))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.line.day") or "/"
        days = super().create(vals_list)
        days.action_refresh()
        return days

    def action_refresh(self):
        """Fill the figures from the day's scans. Reasons typed on hours are kept."""
        for day in self:
            if day.state == "closed":
                raise UserError(_("The day of %s is closed.", day.line_id.name))
            line = day.line_id
            summary = line._garment_daily_summary(day.date)
            board = line._garment_hourly_board(day.date)
            reasons = {h.hour: h.reason for h in day.hour_ids}
            worked = [h for h in board["hours"] if h["output"]]
            bundle = self.env["garment.scan"].search([("line_id", "=", line.id)], limit=1).bundle_id
            day.write({
                "order_id": day.order_id.id or bundle.order_id.id,
                "bulletin_id": day.bulletin_id.id or line.current_bulletin_id.id,
                "working_minutes": line.working_minutes,
                "available_minutes": summary["available_minutes"],
                "earned_minutes": summary["earned_minutes"],
                "planned_efficiency": line.target_efficiency,
                "operators": line.operator_count,
                "pieces": summary["pieces"],
                "target": line.target_per_hour * len(board["hours"]),
                "efficiency": summary["efficiency"],
                "lost_minutes": summary["lost_minutes"],
                "wip_days": summary["wip_days"],
                "dhu": summary["dhu"] or 0.0,
                "hour_ids": [Command.clear()] + [Command.create({
                    "hour": "%s–%02d" % (h["hour"][:2], int(h["hour"][:2]) + 1),
                    "target": h["target"], "output": h["output"], "efficiency": h["efficiency"],
                    "lost_minutes": round(line.operator_count * 60 * (1 - h["efficiency"] / 100))
                    if h["efficiency"] < 100 else 0,
                    "reason": reasons.get("%s–%02d" % (h["hour"][:2], int(h["hour"][:2]) + 1)),
                }) for h in worked],
            })
        return True

    def action_close(self):
        self.action_refresh()
        self.state = "closed"
        return True

    def action_reopen(self):
        self.state = "open"
        return True

    @api.model
    def _garment_cron_daily(self):
        """Create / refresh today's summary for every line with scans today."""
        today = fields.Date.context_today(self)
        for line in self.env["garment.line"].search([]):
            if not line._garment_day_scans(today):
                continue
            day = self.search([("line_id", "=", line.id), ("date", "=", today)], limit=1)
            if day:
                if day.state == "open":
                    day.action_refresh()
            else:
                self.create({"line_id": line.id, "date": today})
        return True


class GarmentLineDayHour(models.Model):
    _name = "garment.line.day.hour"
    _description = "Line Day Hour"
    _order = "day_id, hour"

    day_id = fields.Many2one("garment.line.day", required=True, ondelete="cascade", index=True)
    hour = fields.Char(required=True)
    target = fields.Integer()
    output = fields.Integer()
    efficiency = fields.Float(digits=(16, 0))
    lost_minutes = fields.Integer()
    reason = fields.Char()


class GarmentLineDayDowntime(models.Model):
    _name = "garment.line.day.downtime"
    _description = "Line Day Downtime"

    day_id = fields.Many2one("garment.line.day", required=True, ondelete="cascade", index=True)
    reason = fields.Char(required=True)
    machine_type_id = fields.Many2one("garment.machine.type", string="Machine")
    minutes = fields.Integer()
