from datetime import datetime, time

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

KINDS = [("inline", "Inline"), ("endline", "End-line"), ("final", "Final")]
RESULTS = [
    ("pending", "Pending"),
    ("passed", "Passed"),
    ("failed", "Failed"),
    ("concession", "Accepted under Concession"),
]
POSITIONS = [
    ("collar", "Collar"),
    ("front_left", "Front left"),
    ("front_right", "Front right"),
    ("left_sleeve", "Left sleeve"),
    ("right_sleeve", "Right sleeve"),
    ("back", "Back"),
    ("hem", "Hem"),
    ("side_seams", "Side seams"),
    ("waistband", "Waistband"),
    ("pocket", "Pocket"),
    ("other", "Other"),
]
# Places shown on the end-line tablet (screen 64), in this order.
TABLET_POSITIONS = ["collar", "front_left", "front_right", "left_sleeve", "right_sleeve", "back", "hem", "side_seams"]
# Fallback tablet defects (library codes) when no defect is flagged "On the end-line tablet".
TABLET_DEFECT_CODES = ["W01", "W02", "W04", "W10", "D05", "W07", "S01", "M01"]


class GarmentInspection(models.Model):
    _name = "garment.inspection"
    _description = "Garment Quality Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Inspection", required=True, copy=False, readonly=True, default="New", index=True)
    kind = fields.Selection(KINDS, string="Inspection Type", required=True, default="inline", tracking=True)
    state = fields.Selection([("in_progress", "In Progress"), ("completed", "Completed")], default="in_progress",
                             required=True, tracking=True, copy=False)
    result = fields.Selection(RESULTS, default="pending", required=True, tracking=True, copy=False, index=True)
    fail_reason = fields.Char(string="Failed Because", copy=False, tracking=True)

    order_id = fields.Many2one("garment.order", string="Order", required=True, index=True, check_company=True,
                               domain="[('state', 'not in', ('draft', 'cancel'))]")
    style_id = fields.Many2one(related="order_id.style_id", store=True, string="Style")
    buyer_id = fields.Many2one(related="order_id.buyer_id", store=True, string="Buyer")
    line_id = fields.Many2one("mrp.workcenter", string="Sewing Line", index=True,
                              compute="_compute_line_id", store=True, readonly=False)
    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company,
                                 compute="_compute_company_id", store=True, readonly=False, precompute=True)
    inspector_id = fields.Many2one("res.users", string="Inspector", default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)

    pieces_checked = fields.Integer()
    defect_line_ids = fields.One2many("garment.inspection.defect", "inspection_id", string="Defects", copy=False)
    hour_ids = fields.One2many("garment.inspection.hour", "inspection_id", string="Hourly Counts", copy=False)
    critical_count = fields.Integer(string="Critical", compute="_compute_counts", store=True)
    major_count = fields.Integer(string="Major", compute="_compute_counts", store=True)
    minor_count = fields.Integer(string="Minor", compute="_compute_counts", store=True)
    defect_count = fields.Integer(string="Defects", compute="_compute_counts", store=True)
    dhu = fields.Float(string="DHU", compute="_compute_counts", store=True, digits=(16, 2), aggregator="avg",
                       help="Defects per hundred units = defects × 100 ÷ pieces checked.")

    # Sampling plan (final inspections)
    lot_size = fields.Integer(string="Lot Size")
    aql_major = fields.Float(string="AQL Major", digits=(16, 1),
                             default=lambda self: self.env.company.garment_aql_major)
    aql_minor = fields.Float(string="AQL Minor", digits=(16, 1),
                             default=lambda self: self.env.company.garment_aql_minor)
    code_letter = fields.Char(compute="_compute_sampling_plan", store=True)
    sample_size = fields.Integer(compute="_compute_sampling_plan", store=True)
    major_accept = fields.Integer(compute="_compute_sampling_plan", store=True)
    major_reject = fields.Integer(compute="_compute_sampling_plan", store=True)
    minor_accept = fields.Integer(compute="_compute_sampling_plan", store=True)
    minor_reject = fields.Integer(compute="_compute_sampling_plan", store=True)
    plan_error = fields.Char(compute="_compute_sampling_plan", store=True)
    major_over = fields.Boolean(compute="_compute_over")
    minor_over = fields.Boolean(compute="_compute_over")

    reinspection_of_id = fields.Many2one("garment.inspection", string="Re-inspection of", copy=False,
                                         index=True, check_company=True)
    reinspection_ids = fields.One2many("garment.inspection", "reinspection_of_id", string="Re-inspections")
    reinspection_count = fields.Integer(compute="_compute_link_counts")
    capa_ids = fields.Many2many("garment.capa", "garment_capa_inspection_rel", "inspection_id", "capa_id",
                                string="CAPAs", copy=False)
    capa_count = fields.Integer(compute="_compute_link_counts")
    concession_reason = fields.Text(copy=False, tracking=True)
    concession_user_id = fields.Many2one("res.users", string="Concession by", copy=False, readonly=True)
    note = fields.Html()

    _sql_constraints = [
        ("pieces_checked_positive", "CHECK(pieces_checked >= 0)", "Pieces checked cannot be negative."),
        ("lot_size_positive", "CHECK(lot_size >= 0)", "Lot size cannot be negative."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.inspection") or "New"
        return super().create(vals_list)

    @api.depends("order_id")
    def _compute_line_id(self):
        for insp in self:
            if not insp.line_id and insp.order_id.sewing_line_id:
                insp.line_id = insp.order_id.sewing_line_id

    @api.depends("order_id")
    def _compute_company_id(self):
        for insp in self:
            if insp.order_id:
                insp.company_id = insp.order_id.company_id
            elif not insp.company_id:
                insp.company_id = self.env.company

    @api.depends("defect_line_ids.qty", "defect_line_ids.severity", "pieces_checked")
    def _compute_counts(self):
        for insp in self:
            counts = {"critical": 0, "major": 0, "minor": 0}
            for line in insp.defect_line_ids:
                counts[line.severity or "minor"] += line.qty
            insp.critical_count = counts["critical"]
            insp.major_count = counts["major"]
            insp.minor_count = counts["minor"]
            insp.defect_count = sum(counts.values())
            insp.dhu = self._garment_dhu(insp.defect_count, insp.pieces_checked)

    @api.model
    def _garment_dhu(self, defects, pieces):
        """DHU = defects × 100 ÷ pieces checked (0 when nothing was checked)."""
        return round(defects * 100.0 / pieces, 2) if pieces else 0.0

    @api.depends("kind", "lot_size", "aql_major", "aql_minor")
    def _compute_sampling_plan(self):
        Limit = self.env["garment.aql.limit"]
        for insp in self:
            vals = dict(code_letter=False, sample_size=0, major_accept=0, major_reject=0, minor_accept=0,
                        minor_reject=0, plan_error=False)
            if insp.kind == "final" and insp.lot_size > 0:
                try:
                    major = Limit._garment_lookup(insp.lot_size, insp.aql_major)
                    minor = Limit._garment_lookup(insp.lot_size, insp.aql_minor)
                except UserError as err:
                    vals["plan_error"] = str(err.args[0]) if err.args else str(err)
                else:
                    vals.update(
                        code_letter=major["code_letter"],
                        # One sample for both classes: the larger plan, never more than the lot (100 % check).
                        sample_size=min(max(major["sample_size"], minor["sample_size"]), insp.lot_size),
                        major_accept=major["accept"], major_reject=major["reject"],
                        minor_accept=minor["accept"], minor_reject=minor["reject"],
                    )
            insp.update(vals)

    @api.depends("major_count", "minor_count", "major_accept", "minor_accept", "kind", "sample_size")
    def _compute_over(self):
        for insp in self:
            final = insp.kind == "final" and insp.sample_size
            insp.major_over = bool(final and insp.major_count > insp.major_accept)
            insp.minor_over = bool(final and insp.minor_count > insp.minor_accept)

    @api.depends("reinspection_ids", "capa_ids")
    def _compute_link_counts(self):
        for insp in self:
            insp.reinspection_count = len(insp.reinspection_ids)
            insp.capa_count = len(insp.capa_ids)

    @api.depends("name", "order_id")
    def _compute_display_name(self):
        for insp in self:
            insp.display_name = insp.name or ""

    @api.onchange("order_id", "kind")
    def _onchange_order_lot(self):
        if self.kind == "final" and self.order_id and not self.lot_size:
            self.lot_size = self.order_id.qty_packed or self.order_id.qty_ordered

    @api.constrains("kind", "lot_size", "state")
    def _check_final_lot(self):
        for insp in self:
            if insp.kind == "final" and insp.state == "completed" and insp.lot_size < 1:
                raise ValidationError(self.env._("A final inspection needs a lot size."))

    # ------------------------------------------------------------------ rules
    def _garment_evaluate(self):
        """Result and reason by the inspection rules (no write).

        Final: any critical defect fails; major or minor defects above the accept number fail.
        Inline / end-line: only a critical defect fails (they measure DHU, they do not accept a lot)."""
        self.ensure_one()
        reasons = []
        if self.critical_count:
            reasons.append(self.env._("Critical defect found"))
        if self.kind == "final":
            if self.major_count > self.major_accept:
                reasons.append(self.env._("Major defects above the accept number"))
            if self.minor_count > self.minor_accept:
                reasons.append(self.env._("Minor defects above the accept number"))
        if reasons:
            return "failed", self.env._(" and ").join([reasons[0]] + [r[0].lower() + r[1:] for r in reasons[1:]])
        return "passed", False

    def action_complete(self):
        for insp in self:
            if insp.state != "in_progress":
                raise UserError(self.env._("%s is already completed.", insp.name))
            if insp.pieces_checked < 1:
                raise UserError(self.env._("Enter the pieces checked before completing %s.", insp.name))
            if insp.kind == "final":
                if insp.plan_error:
                    raise UserError(insp.plan_error)
                if not insp.sample_size:
                    raise UserError(self.env._("Enter the lot size to get the sampling plan."))
                if insp.pieces_checked < insp.sample_size:
                    raise UserError(self.env._(
                        "The sampling plan asks for %(n)s pieces; only %(c)s were checked.",
                        n=insp.sample_size, c=insp.pieces_checked))
            result, reason = insp._garment_evaluate()
            insp.write({"state": "completed", "result": result, "fail_reason": reason})
            if insp.kind == "final":
                insp._garment_notify_order()
        return True

    def _garment_notify_order(self):
        self.ensure_one()
        if self.result == "failed":
            body = self.env._("Final inspection %(name)s failed: shipment is blocked until a re-inspection passes.",
                              name=self.name)
        elif self.result == "concession":
            body = self.env._("Final inspection %(name)s accepted under concession by %(user)s: %(reason)s",
                              name=self.name, user=self.env.user.name, reason=self.concession_reason or "")
        else:
            body = self.env._("Final inspection %(name)s passed.", name=self.name)
        self.order_id.sudo().message_post(body=body)

    def action_accept_concession(self):
        self.ensure_one()
        if self.kind != "final" or self.result != "failed":
            raise UserError(self.env._("Only a failed final inspection can be accepted under concession."))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Accept under Concession"),
            "res_model": "garment.inspection.concession.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_inspection_id": self.id},
        }

    def _garment_accept_concession(self, reason):
        """Factory Manager override of a failed final (logged on the inspection and the order)."""
        self.ensure_one()
        if not self.env.user.has_group("zyra_garment_base.group_garment_factory_manager"):
            raise UserError(self.env._("Only a Factory Manager can accept a failed lot under concession."))
        if self.kind != "final" or self.result != "failed":
            raise UserError(self.env._("Only a failed final inspection can be accepted under concession."))
        if not (reason or "").strip():
            raise UserError(self.env._("Give the reason for the concession."))
        self.write({"result": "concession", "concession_reason": reason, "concession_user_id": self.env.user.id})
        self.message_post(body=self.env._("Accepted under concession: %s", reason))
        self._garment_notify_order()
        return True

    def action_reinspect(self):
        self.ensure_one()
        if self.kind != "final" or self.result != "failed":
            raise UserError(self.env._("Only a failed final inspection is re-inspected."))
        new = self.create({
            "kind": "final",
            "order_id": self.order_id.id,
            "line_id": self.line_id.id,
            "lot_size": self.lot_size,
            "aql_major": self.aql_major,
            "aql_minor": self.aql_minor,
            "reinspection_of_id": self.id,
        })
        return new._garment_form_action()

    def action_raise_capa(self):
        self.ensure_one()
        top = self.defect_line_ids.sorted(lambda l: (-l.qty, l.id))[:1]
        ctx = {
            "default_source": self.kind,
            "default_order_id": self.order_id.id,
            "default_style_id": self.style_id.id,
            "default_line_ids": [self.line_id.id] if self.line_id else [],
            "default_inspection_ids": [self.id],
            "default_first_seen": fields.Date.to_date(fields.Datetime.context_timestamp(self, self.date)),
        }
        if top:
            ctx.update({
                "default_defect_id": top.defect_id.id,
                "default_position": top.position,
                "default_occurrences": sum(self.defect_line_ids.filtered(
                    lambda l: l.defect_id == top.defect_id and l.position == top.position).mapped("qty")),
                "default_title": top._garment_title(),
            })
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Raise CAPA"),
            "res_model": "garment.capa",
            "view_mode": "form",
            "target": "current",
            "context": ctx,
        }

    def action_print_report(self):
        return self.env.ref("zyra_garment_quality.action_report_final_inspection").report_action(self)

    def action_view_reinspections(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_quality.action_garment_inspection")
        action.update({"domain": [("reinspection_of_id", "=", self.id)], "context": {}})
        return action

    def action_view_capas(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_quality.action_garment_capa")
        action.update({"domain": [("id", "in", self.capa_ids.ids)], "context": {}})
        if len(self.capa_ids) == 1:
            action.update({"view_mode": "form", "views": [(False, "form")], "res_id": self.capa_ids.id})
        return action

    def _garment_form_action(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "garment.inspection",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------- tablet API
    @api.model
    def _garment_today_start(self):
        """Start of today in the user's time zone, as naive UTC (for Datetime domains)."""
        tz = pytz.timezone(self.env.user.tz or "UTC")
        local_now = datetime.now(tz)
        local_start = tz.localize(datetime.combine(local_now.date(), time.min))
        return local_start.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _garment_hour_start(self, when=None):
        when = when or fields.Datetime.now()
        return when.replace(minute=0, second=0, microsecond=0)

    @api.model
    def _garment_running_order(self, line):
        return self.env["garment.order"].search([
            ("sewing_line_id", "=", line.id),
            ("state", "in", ("confirmed", "in_production", "packed")),
        ], order="ex_factory_date, id", limit=1)

    @api.model
    def garment_endline_lines(self):
        """Lines the tablet can check: every sewing line with an open order."""
        orders = self.env["garment.order"].search([
            ("sewing_line_id", "!=", False), ("state", "in", ("confirmed", "in_production", "packed"))])
        lines = orders.mapped("sewing_line_id").sorted(lambda l: (l.name or "", l.id))
        return [{"id": line.id, "name": line.name, "order": self._garment_running_order(line).display_name}
                for line in lines]

    @api.model
    def _garment_tablet_defects(self):
        Defect = self.env["garment.defect"]
        defects = Defect.search([("endline_button", "=", True)], order="endline_sequence, sequence, id")
        if not defects:
            defects = Defect.search([("code", "in", TABLET_DEFECT_CODES)])
            defects = defects.sorted(lambda d: TABLET_DEFECT_CODES.index(d.code))
        if not defects:
            defects = Defect.search([("department", "=", "sewing")], limit=8)
        return defects

    @api.model
    def garment_endline_stats(self, line_id):
        line = self.env["mrp.workcenter"].browse(line_id)
        company = self.env.company
        hour = self._garment_hour_start()
        buckets = self.env["garment.inspection.hour"].search([
            ("line_id", "=", line.id), ("hour_start", "=", hour), ("kind", "=", "endline")])
        hour_pieces = sum(buckets.mapped("pieces"))
        hour_defects = sum(buckets.mapped("defects"))
        today = self.search([("kind", "=", "endline"), ("line_id", "=", line.id),
                             ("date", ">=", self._garment_today_start())])
        today_pieces = sum(today.mapped("pieces_checked"))
        today_defects = sum(today.mapped("defect_count"))
        return {
            "hour_checked": hour_pieces,
            "hour_dhu": self._garment_dhu(hour_defects, hour_pieces),
            "today_checked": today_pieces,
            "today_dhu": self._garment_dhu(today_defects, today_pieces),
            "limit": company.garment_dhu_limit,
        }

    @api.model
    def garment_endline_state(self, line_id):
        line = self.env["mrp.workcenter"].browse(line_id).exists()
        if not line:
            raise UserError(self.env._("This sewing line no longer exists."))
        order = self._garment_running_order(line)
        labels = dict(POSITIONS)
        return {
            "line": {"id": line.id, "name": line.name},
            "order": {"id": order.id, "name": order.display_name} if order else False,
            "positions": [{"key": key, "label": labels[key]} for key in TABLET_POSITIONS],
            "defects": [{"id": d.id, "label": d.endline_label or d.name, "severity": d.severity}
                        for d in self._garment_tablet_defects()],
            "stats": self.garment_endline_stats(line.id),
        }

    @api.model
    def _garment_endline_session(self, line):
        """Today's open end-line inspection of the line's running order (created on the first tap)."""
        order = self._garment_running_order(line)
        if not order:
            raise UserError(self.env._("No open production order runs on %s.", line.name))
        session = self.search([
            ("kind", "=", "endline"), ("line_id", "=", line.id), ("order_id", "=", order.id),
            ("state", "=", "in_progress"), ("date", ">=", self._garment_today_start()),
        ], order="date desc, id desc", limit=1)
        if not session:
            session = self.create({"kind": "endline", "order_id": order.id, "line_id": line.id})
        return session

    @api.model
    def garment_endline_record(self, line_id, defect_id=False, position=False):
        """One piece checked at the end of the line: good (no defect) or with one defect at ``position``.

        Counts the piece on today's end-line inspection and in the current hour; a defect adds a defect
        line (which may raise a CAPA). Returns fresh tablet stats."""
        line = self.env["mrp.workcenter"].browse(line_id).exists()
        if not line:
            raise UserError(self.env._("This sewing line no longer exists."))
        if defect_id and position not in dict(POSITIONS):
            raise UserError(self.env._("Tap where the defect is."))
        session = self._garment_endline_session(line)
        session.pieces_checked += 1
        self.env["garment.inspection.hour"]._garment_add(session, 1, 1 if defect_id else 0)
        if defect_id:
            self.env["garment.inspection.defect"].create({
                "inspection_id": session.id, "defect_id": defect_id, "position": position, "qty": 1})
        return self.garment_endline_stats(line.id)
