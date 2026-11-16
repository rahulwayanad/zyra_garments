from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

SAMPLE_OPEN_STATES = ("requested", "in_progress", "rejected", "with_buyer")


class GarmentSample(models.Model):
    """A sample of a style: proto, fit, size set, pre-production, top of production …"""

    _name = "garment.sample"
    _description = "Garment Sample"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "required_date, id desc"
    _check_company_auto = True

    name = fields.Char(string="Sample No.", required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    state = fields.Selection([
        ("requested", "Requested"),
        ("in_progress", "In the Sample Room"),
        ("rejected", "Rejected, Remake Due"),
        ("with_buyer", "With the Buyer"),
        ("approved", "Approved"),
    ], default="requested", required=True, tracking=True, group_expand="_group_expand_state", index=True)
    sample_type = fields.Selection([
        ("proto", "Proto sample"),
        ("fit", "Fit sample"),
        ("size_set", "Size set sample"),
        ("pp", "Pre-production sample"),
        ("top", "Top of production sample"),
        ("salesman", "Salesman sample"),
        ("shipment", "Shipment sample"),
    ], string="Sample Type", required=True, default="proto", tracking=True)
    sample_type_short = fields.Char(compute="_compute_sample_type_short")

    style_id = fields.Many2one("garment.style", string="Style", required=True, index=True, tracking=True,
                               check_company=True)
    image_128 = fields.Image(related="style_id.image_128")
    order_id = fields.Many2one("garment.order", string="Production Order", index=True, check_company=True,
                               domain="[('style_id', '=', style_id)]")
    buyer_id = fields.Many2one("res.partner", string="Buyer", compute="_compute_buyer", store=True,
                               readonly=False, domain="[('is_garment_buyer', '=', True)]")
    colour_id = fields.Many2one("garment.colour", string="Colourway")
    size_ids = fields.Many2many("garment.size", string="Sizes")
    size_names = fields.Char(string="Sizes in Order", compute="_compute_size_names")
    size_measured_id = fields.Many2one("garment.size", string="Size Measured")
    pieces = fields.Integer(default=1)
    merchandiser_id = fields.Many2one("res.users", string="Merchandiser", default=lambda self: self.env.user,
                                      tracking=True)

    request_date = fields.Date(string="Requested On", default=fields.Date.context_today, required=True)
    required_date = fields.Date(string="Required By", tracking=True)
    sent_date = fields.Date(string="Sent to Buyer On", tracking=True)
    decision_date = fields.Date(string="Decision On", tracking=True)
    round = fields.Integer(string="Round No.", default=1, required=True, tracking=True)
    courier = fields.Char()
    tracking_ref = fields.Char(string="Tracking Ref.")
    cost = fields.Monetary(string="Sample Cost")
    charge_to_buyer = fields.Boolean(string="Charge to Buyer")
    charge_label = fields.Char(string="Charge to Buyer?", compute="_compute_charge_label")
    invoice_id = fields.Many2one("account.move", string="Invoice", copy=False, readonly=True)
    buyer_comments = fields.Text(string="Buyer Comments")

    measurement_ids = fields.One2many("garment.sample.measurement", "sample_id", string="Measurements",
                                      copy=False)
    round_ids = fields.One2many("garment.sample.round", "sample_id", string="Rounds", copy=False)
    points_measured = fields.Integer(compute="_compute_measure_kpis",
                                     help="Points of measure measured in the current round.")
    points_out = fields.Integer(string="Out of Tolerance", compute="_compute_measure_kpis")
    is_overdue = fields.Boolean(compute="_compute_overdue", search="_search_overdue")

    @api.model
    def _group_expand_state(self, states, domain):
        """Kanban columns: the open states in board order, plus approved when it holds cards."""
        order = ["in_progress", "rejected", "requested", "with_buyer"]
        return order + [s for s in states if s not in order]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(
                    vals.get("company_id") or self.env.company.id).next_by_code("garment.sample") or _("New")
        return super().create(vals_list)

    @api.depends("style_id.code", "name", "sample_type")
    def _compute_display_name(self):
        labels = dict(self._fields["sample_type"]._description_selection(self.env))
        for s in self:
            s.display_name = " · ".join(p for p in (s.name, s.style_id.code, labels.get(s.sample_type)) if p)

    @api.depends("sample_type")
    def _compute_sample_type_short(self):
        short = {"proto": "Proto", "fit": "Fit", "size_set": "Size set", "pp": "PP", "top": "TOP",
                 "salesman": "SMS", "shipment": "Shipment"}
        for s in self:
            s.sample_type_short = short.get(s.sample_type, "")

    @api.depends("order_id.buyer_id", "style_id.buyer_id")
    def _compute_buyer(self):
        for s in self:
            s.buyer_id = s.order_id.buyer_id or s.style_id.buyer_id or s.buyer_id

    @api.depends("charge_to_buyer")
    def _compute_charge_label(self):
        for s in self:
            s.charge_label = _("Yes") if s.charge_to_buyer else _("No")

    @api.depends("size_ids")
    def _compute_size_names(self):
        for s in self:
            s.size_names = " · ".join(s.size_ids.sorted(lambda z: (z.sequence, z.id)).mapped("name"))

    @api.depends("measurement_ids.result", "measurement_ids.round", "round")
    def _compute_measure_kpis(self):
        for s in self:
            current = s.measurement_ids.filtered(lambda m: m.round == s.round and m.result != "pending")
            s.points_measured = len(current)
            s.points_out = len(current.filtered(lambda m: m.result == "fail"))

    @api.depends("required_date", "state")
    def _compute_overdue(self):
        today = fields.Date.context_today(self)
        for s in self:
            s.is_overdue = s._is_overdue_on(today)

    def _is_overdue_on(self, day):
        """Rule: a sample is overdue when its required date has passed and it has not reached the buyer."""
        self.ensure_one()
        return bool(self.required_date and self.required_date < day
                    and self.state in ("requested", "in_progress", "rejected"))

    def _search_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        ids = self.search([("required_date", "<", today),
                           ("state", "in", ["requested", "in_progress", "rejected"])]).ids
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", ids)]

    @api.onchange("order_id")
    def _onchange_order_id(self):
        if self.order_id:
            self.style_id = self.order_id.style_id
            if not self.size_ids:
                self.size_ids = self.order_id.size_ids

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_start(self):
        for s in self:
            if s.state not in ("requested", "rejected"):
                raise UserError(_("Only a requested or rejected sample can go into the sample room."))
            s.state = "in_progress"

    def action_send_to_buyer(self):
        for s in self:
            if s.state not in ("requested", "in_progress"):
                raise UserError(_("Only a sample in the sample room can be sent to the buyer."))
            s.write({"state": "with_buyer", "sent_date": s.sent_date or fields.Date.context_today(s)})

    def _log_round(self, decision):
        for s in self:
            self.env["garment.sample.round"].create({
                "sample_id": s.id,
                "round": s.round,
                "sent_date": s.sent_date,
                "decision_date": s.decision_date,
                "decision": decision,
                "points_measured": s.points_measured,
                "points_out": s.points_out,
                "comments": s.buyer_comments,
            })

    def action_approve(self):
        for s in self:
            if s.state != "with_buyer":
                raise UserError(_("Only a sample with the buyer can be approved."))
            s.decision_date = s.decision_date or fields.Date.context_today(s)
            s._log_round("approved")
            s.state = "approved"
            s.message_post(body=_("%(type)s %(name)s approved in round %(round)s.",
                                  type=dict(s._fields["sample_type"]._description_selection(s.env))[s.sample_type],
                                  name=s.name, round=s.round))

    def action_reject(self):
        for s in self:
            if s.state != "with_buyer":
                raise UserError(_("Only a sample with the buyer can be rejected."))
            s.decision_date = s.decision_date or fields.Date.context_today(s)
            s._log_round("rejected")
            s.state = "rejected"

    def action_remake(self):
        """Start the next round of a rejected sample: round + 1, dates cleared, back to the sample room."""
        for s in self:
            if s.state != "rejected":
                raise UserError(_("Only a rejected sample can be remade."))
            s.write({"round": s.round + 1, "state": "in_progress", "sent_date": False, "decision_date": False,
                     "buyer_comments": False})

    def action_load_spec(self):
        """Fill the measurement sheet of the current round from the tech pack's graded chart."""
        for s in self:
            techpack = (s.order_id.techpack_id or s.style_id.current_techpack_id)
            size = s.size_measured_id
            if not techpack or not size:
                raise UserError(_("Set the size measured and make sure the style has a tech pack."))
            chart = techpack.get_graded_chart() if hasattr(techpack, "get_graded_chart") else {}
            existing = s.measurement_ids.filtered(lambda m: m.round == s.round).mapped("pom_id")
            cmds = []
            for meas in techpack.measurement_ids:
                if meas.pom_id in existing:
                    continue
                pom_chart = chart.get(meas.pom_id.id, {})
                spec = pom_chart.get(size.id, meas.base_value)
                cmds.append(Command.create({
                    "round": s.round,
                    "pom_id": meas.pom_id.id,
                    "size_id": size.id,
                    "spec": spec,
                    "tol_plus": meas.tol_plus,
                    "tol_minus": meas.tol_minus,
                }))
            s.measurement_ids = cmds
        return True

    def action_invoice_cost(self):
        self.ensure_one()
        if not self.charge_to_buyer:
            raise UserError(_("This sample is not charged to the buyer."))
        if self.invoice_id:
            raise UserError(_("The sample cost is already invoiced (%s).", self.invoice_id.display_name))
        if not self.cost:
            raise UserError(_("Enter the sample cost first."))
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.buyer_id.id,
            "invoice_origin": self.name,
            "invoice_line_ids": [Command.create({
                "name": _("Sample %(name)s – %(style)s", name=self.name, style=self.style_id.display_name),
                "quantity": 1,
                "price_unit": self.cost,
            })],
        })
        self.invoice_id = move
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": move.id,
                "view_mode": "form"}


class GarmentSampleMeasurement(models.Model):
    """One point of measure of a sample: spec from the graded chart, measured value and verdict."""

    _name = "garment.sample.measurement"
    _description = "Sample Fit Measurement"
    _order = "sample_id, round, sequence, id"

    sample_id = fields.Many2one("garment.sample", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    round = fields.Integer(default=1, required=True)
    pom_id = fields.Many2one("garment.pom", string="Point of Measure", required=True)
    size_id = fields.Many2one("garment.size", string="Size")
    spec = fields.Float(digits=(16, 2))
    tol_plus = fields.Float(string="Tol +", digits=(16, 2))
    tol_minus = fields.Float(string="Tol −", digits=(16, 2))
    measured = fields.Float(digits=(16, 2))
    is_measured = fields.Boolean(string="Measured?", compute="_compute_result", store=True)
    deviation = fields.Float(digits=(16, 2), compute="_compute_result", store=True)
    result = fields.Selection([
        ("pending", "Not measured"),
        ("pass", "In tolerance"),
        ("fail", "Out of tolerance"),
    ], compute="_compute_result", store=True)

    @api.depends("spec", "measured", "tol_plus", "tol_minus")
    def _compute_result(self):
        for m in self:
            if not m.measured:
                m.is_measured = False
                m.deviation = 0.0
                m.result = "pending"
                continue
            m.is_measured = True
            m.deviation = round(m.measured - m.spec, 2)
            m.result = "pass" if m._within_tolerance(m.deviation) else "fail"

    def _within_tolerance(self, deviation):
        """Rule: a point passes when the deviation from spec is within its tolerance (+ above, − below)."""
        self.ensure_one()
        eps = 1e-6
        if deviation >= 0:
            return deviation <= self.tol_plus + eps
        return -deviation <= self.tol_minus + eps

    @api.constrains("tol_plus", "tol_minus")
    def _check_tolerance(self):
        for m in self:
            if m.tol_plus < 0 or m.tol_minus < 0:
                raise ValidationError(_("Tolerances are entered as positive numbers."))


class GarmentSampleRound(models.Model):
    """History of the rounds of a sample (one line per buyer decision)."""

    _name = "garment.sample.round"
    _description = "Sample Round"
    _order = "sample_id, round"

    sample_id = fields.Many2one("garment.sample", required=True, ondelete="cascade", index=True)
    round = fields.Integer(required=True)
    sent_date = fields.Date(string="Sent On")
    decision_date = fields.Date(string="Decision On")
    decision = fields.Selection([("approved", "Approved"), ("rejected", "Rejected")], required=True)
    points_measured = fields.Integer()
    points_out = fields.Integer(string="Out of Tolerance")
    comments = fields.Text()
