from odoo import _, api, fields, models


class GarmentTnaTemplate(models.Model):
    """Time-and-action template: milestones laid back from the ex-factory date."""

    _name = "garment.tna.template"
    _description = "Time and Action Template"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company,
                                 help="Leave empty to share the template with every company.")
    line_ids = fields.One2many("garment.tna.template.line", "template_id", string="Milestones", copy=True)
    lead_days = fields.Integer(string="Lead Time (days)", compute="_compute_lead_days",
                               help="Days from the first milestone to the ex-factory date.")

    @api.depends("line_ids.days_before_ex_factory")
    def _compute_lead_days(self):
        for t in self:
            t.lead_days = max(t.line_ids.mapped("days_before_ex_factory") or [0])


class GarmentTnaTemplateLine(models.Model):
    _name = "garment.tna.template.line"
    _description = "Time and Action Template Milestone"
    _order = "template_id, sequence, id"

    template_id = fields.Many2one("garment.tna.template", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Milestone", required=True, translate=True)
    days_before_ex_factory = fields.Integer(
        string="Days Before Ex-factory", required=True,
        help="Planned date = ex-factory date minus these days (0 = on the ex-factory date).")
    owner_id = fields.Many2one("res.users", string="Default Owner",
                               help="Empty: the merchandiser of the order.")


class GarmentTnaMilestone(models.Model):
    """One milestone of an order's time-and-action plan."""

    _name = "garment.tna.milestone"
    _description = "Time and Action Milestone"
    _order = "order_id, planned_date, sequence, id"

    order_id = fields.Many2one("garment.order", string="Production Order", required=True, ondelete="cascade",
                               index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Milestone", required=True)
    template_line_id = fields.Many2one("garment.tna.template.line", ondelete="set null")
    days_before_ex_factory = fields.Integer(string="Days Before Ex-factory")
    planned_date = fields.Date(string="Planned", required=True)
    actual_date = fields.Date(string="Actual")
    owner_id = fields.Many2one("res.users", string="Owner")
    status = fields.Selection([
        ("pending", "Pending"),
        ("on_time", "On time"),
        ("late", "Late"),
        ("overdue", "Overdue"),
    ], compute="_compute_status", search="_search_status")
    delay_days = fields.Integer(string="Days Late", compute="_compute_status")
    status_label = fields.Char(string="Status Label", compute="_compute_status")

    @api.depends("planned_date", "actual_date")
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for m in self:
            m.status, m.delay_days = m._status_on(today)
            if m.status == "late":
                m.status_label = _("Late %s d", m.delay_days)
            elif m.status == "overdue":
                m.status_label = _("Overdue")
            elif m.status == "on_time":
                m.status_label = _("On time")
            else:
                m.status_label = _("Due in %s d", (m.planned_date - today).days) if m.planned_date else ""

    def _status_on(self, day):
        """Rule: done on or before the planned date = on time; done after = late by the gap;
        not done and planned date passed = overdue; otherwise pending. Returns (status, days late)."""
        self.ensure_one()
        if self.actual_date:
            gap = (self.actual_date - self.planned_date).days if self.planned_date else 0
            return ("late", gap) if gap > 0 else ("on_time", 0)
        if self.planned_date and self.planned_date < day:
            return "overdue", (day - self.planned_date).days
        return "pending", 0

    def _search_status(self, operator, value):
        today = fields.Date.context_today(self)
        values = value if isinstance(value, (list, tuple)) else [value]
        ids = self.search([]).filtered(lambda m: m._status_on(today)[0] in values).ids
        return [("id", "in" if operator in ("=", "in") else "not in", ids)]

    def action_mark_done(self):
        for m in self:
            if not m.actual_date:
                m.actual_date = fields.Date.context_today(m)
        return True
