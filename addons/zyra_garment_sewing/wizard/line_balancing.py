from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class GarmentLineBalancing(models.Model):
    """Line balancing record (screen 55). Rules:
    pitch time = balanced SAM ÷ operators available; target / hour = operators × 60 ÷ SAM × planned efficiency;
    operators needed per station = SAM ÷ pitch; assigned = needed rounded to half operators (min 0.5);
    station capacity / h = assigned × 60 ÷ SAM × station efficiency; balanced output = lowest station capacity
    (the bottleneck); balance loss % = (1 − balanced output ÷ target per hour) × 100."""
    _name = "garment.line.balancing"
    _inherit = ["mail.thread"]
    _description = "Line Balancing"
    _order = "id desc"

    name = fields.Char(default="/", readonly=True, copy=False)
    state = fields.Selection([("draft", "Draft"), ("applied", "Applied"), ("cancel", "Cancelled")],
                             default="draft", required=True, tracking=True)
    order_id = fields.Many2one("garment.order", string="Order")
    bulletin_id = fields.Many2one("garment.bulletin", string="Operation Bulletin", required=True)
    style_id = fields.Many2one(related="bulletin_id.style_id")
    line_id = fields.Many2one("garment.line", string="Sewing Line")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    balanced_on = fields.Date(default=fields.Date.context_today)
    balanced_by = fields.Many2one("res.users", default=lambda self: self.env.user)
    operators = fields.Float(string="Operators Available", digits=(16, 1), required=True, default=7)
    planned_efficiency = fields.Float(string="Planned Efficiency %", digits=(16, 2), default=65.0)
    total_sam = fields.Float(string="Balanced SAM (min)", digits=(16, 2), compute="_compute_balance", store=True)
    pitch_time = fields.Float(string="Pitch Time (min)", digits=(16, 3), compute="_compute_balance", store=True)
    target_output = fields.Float(string="Target / Hour", digits=(16, 1), compute="_compute_balance", store=True)
    balanced_output = fields.Float(string="Balanced Output / Hour", digits=(16, 0), compute="_compute_balance",
                                   store=True)
    balance_loss = fields.Float(string="Balance Loss %", digits=(16, 1), compute="_compute_balance", store=True)
    operators_allocated = fields.Float(string="Operators Assigned", digits=(16, 1), compute="_compute_balance",
                                       store=True)
    bottleneck = fields.Char(compute="_compute_balance", store=True)
    title = fields.Char(compute="_compute_title")
    station_ids = fields.One2many("garment.line.balancing.station", "balancing_id", string="Stations")
    notes = fields.Html()

    @api.depends("order_id", "style_id")
    def _compute_title(self):
        for rec in self:
            rec.title = " · ".join(filter(None, [rec.order_id.name, rec.style_id.code or rec.style_id.name]))

    @api.depends("station_ids.sam", "station_ids.capacity", "station_ids.assigned", "operators",
                 "planned_efficiency")
    def _compute_balance(self):
        for rec in self:
            sam = sum(rec.station_ids.mapped("sam"))
            rec.total_sam = sam
            rec.pitch_time = sam / rec.operators if rec.operators else 0.0
            rec.target_output = rec.operators * 60 / sam * rec.planned_efficiency / 100 if sam else 0.0
            neck = rec.station_ids.filtered("sam").sorted("capacity")[:1]
            rec.balanced_output = neck.capacity
            rec.bottleneck = neck.name or False
            rec.balance_loss = round((1 - neck.capacity / rec.target_output) * 100, 1) \
                if rec.target_output and neck else 0.0
            rec.operators_allocated = sum(rec.station_ids.mapped("assigned"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.line.balancing") or "/"
        records = super().create(vals_list)
        records.filtered(lambda r: not r.station_ids).action_propose()
        return records

    @api.model
    def _garment_assign(self, sams, operators):
        """Pure maths: operators needed (SAM ÷ pitch) and assigned (rounded to 0.5, min 0.5; trimmed by
        0.5 on the stations with most slack while above the operators available)."""
        total = sum(sams)
        if not total or operators <= 0:
            return [0.0] * len(sams), [0.0] * len(sams)
        pitch = total / operators
        needed = [s / pitch for s in sams]
        assigned = [max(0.5, round(n * 2) / 2) for n in needed]
        while sum(assigned) > operators + 1e-9:
            candidates = [i for i, a in enumerate(assigned) if a > 0.5]
            if not candidates:
                break
            i = min(candidates, key=lambda k: sams[k] / (assigned[k] - 0.5))
            assigned[i] -= 0.5
        return needed, assigned

    def action_propose(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only a draft balancing can be re-proposed."))
            lines = rec.bulletin_id.line_ids
            needed, assigned = self._garment_assign(lines.mapped("sam"), rec.operators)
            rec.station_ids = [Command.clear()] + [Command.create({
                "sequence": (i + 1) * 10, "name": line.name, "machine_type_id": line.machine_type_id.id,
                "sam": line.sam, "needed": needed[i], "assigned": assigned[i],
                "efficiency": rec.planned_efficiency}) for i, line in enumerate(lines)]
        return True

    def action_apply(self):
        for rec in self:
            if not rec.line_id:
                raise UserError(_("Choose the sewing line first."))
            rec.line_id.write({"current_bulletin_id": rec.bulletin_id.id,
                               "operator_count": round(rec.operators),
                               "target_efficiency": rec.planned_efficiency})
            rec.state = "applied"
            rec.message_post(body=_("Applied to %(line)s: %(n)s workstations, %(out)s pieces an hour, bottleneck "
                                    "%(neck)s.", line=rec.line_id.name, n=len(rec.station_ids),
                                    out=int(rec.balanced_output), neck=rec.bottleneck or "-"))
        return True

    def action_cancel(self):
        self.state = "cancel"
        return True

    def action_draft(self):
        self.state = "draft"
        return True


class GarmentLineBalancingStation(models.Model):
    _name = "garment.line.balancing.station"
    _description = "Line Balancing Station"
    _order = "balancing_id, sequence, id"

    balancing_id = fields.Many2one("garment.line.balancing", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Bulletin Operation", required=True)
    machine_type_id = fields.Many2one("garment.machine.type", string="Machine")
    sam = fields.Float(string="SAM", digits=(16, 3))
    needed = fields.Float(string="Operators Needed", digits=(16, 2))
    assigned = fields.Float(digits=(16, 1))
    employee_ids = fields.Many2many("hr.employee", string="Operators")
    efficiency = fields.Float(string="Station Eff.", digits=(16, 2), default=65.0)
    capacity = fields.Float(string="Capacity / H", digits=(16, 1), compute="_compute_capacity", store=True)
    is_bottleneck = fields.Boolean(compute="_compute_bottleneck")

    @api.depends("assigned", "sam", "efficiency")
    def _compute_capacity(self):
        for st in self:
            st.capacity = st.assigned * 60 / st.sam * st.efficiency / 100 if st.sam else 0.0

    @api.depends("balancing_id.bottleneck", "name")
    def _compute_bottleneck(self):
        for st in self:
            st.is_bottleneck = bool(st.name and st.name == st.balancing_id.bottleneck)
