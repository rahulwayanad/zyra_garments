from odoo import api, fields, models
from odoo.exceptions import UserError

from .garment_inspection import POSITIONS

SOURCES = [
    ("inline", "Inline"),
    ("endline", "End-line"),
    ("final", "Final"),
    ("buyer", "Buyer complaint"),
    ("other", "Other"),
]
SOURCE_PLURAL = {"inline": "Inline checks", "endline": "End-line checks", "final": "Final inspections"}


class GarmentCapa(models.Model):
    _name = "garment.capa"
    _description = "Corrective and Preventive Action"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "state_sequence, due_date, id desc"
    _check_company_auto = True

    name = fields.Char(string="CAPA", required=True, copy=False, readonly=True, default="New", index=True)
    title = fields.Char(required=True, tracking=True)
    state = fields.Selection([
        ("open", "Open"), ("in_progress", "In Progress"), ("verified", "Verified"), ("closed", "Closed"),
    ], default="open", required=True, tracking=True, group_expand=True)
    state_sequence = fields.Integer(compute="_compute_state_sequence", store=True)
    source = fields.Selection(SOURCES, required=True, default="endline", tracking=True)
    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)

    defect_id = fields.Many2one("garment.defect", string="Defect", tracking=True)
    position = fields.Selection(POSITIONS, string="Where")
    defect_label = fields.Char(string="Defect ", compute="_compute_labels")
    line_ids = fields.Many2many("mrp.workcenter", string="Sewing Lines")
    lines_affected = fields.Integer(compute="_compute_labels")
    raised_from = fields.Char(compute="_compute_labels")
    style_id = fields.Many2one("garment.style", string="Style")
    order_id = fields.Many2one("garment.order", string="Order", check_company=True)
    inspection_ids = fields.Many2many("garment.inspection", "garment_capa_inspection_rel", "capa_id",
                                      "inspection_id", string="Inspections")
    first_seen = fields.Date(default=fields.Date.context_today)
    occurrences = fields.Integer(tracking=True)
    occurrence_days = fields.Integer(string="Over days", default=1)
    occurrences_label = fields.Char(string="Occurrences ", compute="_compute_labels")
    auto_raised = fields.Boolean(readonly=True)

    root_cause = fields.Text(tracking=True)
    action = fields.Text(tracking=True)
    owner_id = fields.Many2one("res.users", string="Owner", tracking=True)
    due_date = fields.Date(string="Due", tracking=True)
    due_in_days = fields.Integer(string="Due in", compute="_compute_due_in")
    verification = fields.Char(help="How the fix is proven, e.g. DHU below 2 % for 3 days.")
    date_closed = fields.Date(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.capa") or "New"
        return super().create(vals_list)

    @api.depends("state")
    def _compute_state_sequence(self):
        order = {"open": 1, "in_progress": 2, "verified": 3, "closed": 4}
        for capa in self:
            capa.state_sequence = order.get(capa.state, 9)

    @api.depends("defect_id", "position", "line_ids", "source", "occurrences", "occurrence_days")
    def _compute_labels(self):
        where = dict(POSITIONS)
        sources = dict(SOURCES)
        for capa in self:
            name = capa.defect_id.endline_label or capa.defect_id.name or ""
            capa.defect_label = " · ".join(p for p in (name, where.get(capa.position, "").lower()) if p)
            capa.lines_affected = len(capa.line_ids)
            lines = ", ".join((l.name or "").split(" · ")[0] for l in capa.line_ids)
            capa.raised_from = ", ".join(p for p in (SOURCE_PLURAL.get(capa.source) or sources.get(capa.source),
                                                      lines) if p)
            days = max(capa.occurrence_days, 1)
            capa.occurrences_label = self.env._("%(n)s in %(d)s days", n=capa.occurrences, d=days) if days > 1 \
                else self.env._("%(n)s in 1 day", n=capa.occurrences)

    @api.depends("due_date")
    def _compute_due_in(self):
        today = fields.Date.context_today(self)
        for capa in self:
            capa.due_in_days = (capa.due_date - today).days if capa.due_date else 0

    @api.model
    def _garment_raise_from_defects(self, defect_lines, total, window_days):
        """Create the CAPA for a repeated defect (called by the trigger on defect lines)."""
        first = min(defect_lines.mapped("date"))
        sample = defect_lines.sorted("date")[-1]
        line = sample.line_id
        capa = self.create({
            "title": sample._garment_title(),
            "source": sample.kind if sample.kind in dict(SOURCES) else "other",
            "company_id": sample.company_id.id,
            "defect_id": sample.defect_id.id,
            "position": sample.position,
            "line_ids": [(6, 0, line.ids)],
            "style_id": sample.style_id.id,
            "order_id": sample.order_id.id,
            "inspection_ids": [(6, 0, defect_lines.mapped("inspection_id").ids)],
            "first_seen": fields.Date.to_date(fields.Datetime.context_timestamp(self, first)),
            "occurrences": total,
            "occurrence_days": window_days,
            "auto_raised": True,
        })
        capa.message_post(body=self.env._(
            "Raised automatically: the same defect was recorded %(n)s times on %(line)s in %(d)s days.",
            n=total, line=(line.name or "").split(" · ")[0], d=window_days), author_id=self.env.ref("base.partner_root").id)
        return capa

    def action_start(self):
        self.filtered(lambda c: c.state == "open").write({"state": "in_progress"})
        return True

    def action_verify(self):
        for capa in self:
            if capa.state != "in_progress":
                raise UserError(self.env._("Only a CAPA in progress can be verified."))
            capa._garment_check_filled()
        self.write({"state": "verified"})
        return True

    def action_close(self):
        for capa in self:
            if capa.state not in ("in_progress", "verified"):
                raise UserError(self.env._("Start the CAPA before closing it."))
            capa._garment_check_filled()
        self.write({"state": "closed", "date_closed": fields.Date.context_today(self)})
        return True

    def action_reopen(self):
        self.write({"state": "in_progress", "date_closed": False})
        return True

    def _garment_check_filled(self):
        if not (self.root_cause and self.action and self.owner_id):
            raise UserError(self.env._("Fill the root cause, the action and the owner of %s first.", self.name))

    def action_view_inspections(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_quality.action_garment_inspection")
        action.update({"domain": [("id", "in", self.inspection_ids.ids)], "context": {}})
        return action

    def action_print_report(self):
        return self.env.ref("zyra_garment_quality.action_report_capa").report_action(self)
