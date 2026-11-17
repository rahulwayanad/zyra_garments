from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

LENGTH_BANDS = [
    ("1", "Up to 3 in"),
    ("2", "3 to 6 in"),
    ("3", "6 to 9 in"),
    ("4", "Over 9 in"),
]
RESULTS = [("pass", "Pass"), ("hold", "On hold"), ("reject", "Reject")]


class GarmentFabricInspection(models.Model):
    """4-point inspection of one fabric roll."""

    _name = "garment.fabric.inspection"
    _description = "Fabric Inspection (4-point)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_inspected desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Inspection", required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _("New"))
    state = fields.Selection([("in_progress", "In Progress"), ("done", "Done")], default="in_progress",
                             required=True, tracking=True, copy=False, index=True)
    lot_id = fields.Many2one("stock.lot", string="Roll", required=True, index=True, check_company=True,
                             domain="[('is_fabric_roll', '=', True)]", tracking=True)
    company_id = fields.Many2one("res.company", required=True, index=True,
                                 default=lambda self: self.env.company)
    product_id = fields.Many2one(related="lot_id.product_id", store=True, string="Fabric")
    supplier_id = fields.Many2one(related="lot_id.roll_supplier_id", store=True, string="Supplier")
    dye_lot = fields.Char(related="lot_id.dye_lot", string="Dye Lot")
    garment_order_id = fields.Many2one(related="lot_id.garment_order_id", store=True, string="Production Order")
    roll_length = fields.Float(related="lot_id.roll_received_qty", string="Roll Length")
    roll_uom_id = fields.Many2one(related="lot_id.product_uom_id", string="Roll Unit")
    roll_colour_label = fields.Char(related="lot_id.roll_colour_label")

    inspector_id = fields.Many2one("res.users", string="Inspector", default=lambda self: self.env.user)
    date_inspected = fields.Date(string="Inspected On", default=fields.Date.context_today, required=True)
    frame = fields.Char(string="Frame", default="Frame 1", help="Inspection machine / table.")

    inspected_length_yd = fields.Float(string="Inspected Length (yd)", digits=(16, 2))
    cuttable_width_in = fields.Float(string="Cuttable Width (in)", digits=(16, 2))
    width_measured_in = fields.Float(string="Width Measured (in)", digits=(16, 2))
    gsm_measured = fields.Float(string="GSM Measured", digits=(16, 1))
    current_yard = fields.Float(string="Current Yard", digits=(16, 1),
                                help="Position on the frame; the tablet stamps it on each defect.")

    defect_line_ids = fields.One2many("garment.fabric.inspection.defect", "inspection_id", string="Defects")
    defect_count = fields.Integer(string="Defect Count", compute="_compute_points", store=True)
    penalty_points = fields.Integer(string="Penalty Points", compute="_compute_points", store=True)
    points_per_100sqyd = fields.Float(string="Pts / 100 sq yd", digits=(16, 1), compute="_compute_points",
                                      store=True)
    accept_limit = fields.Float(string="Accept Limit", digits=(16, 1),
                                default=lambda self: self.env.company.garment_fabric_accept_points)
    result_auto = fields.Selection([("pass", "Pass"), ("hold", "On hold")], string="Verdict by Points",
                                   compute="_compute_result", store=True)
    result_override = fields.Selection([("hold", "On hold"), ("reject", "Reject")], string="Inspector Decision",
                                       help="Hold or reject the roll whatever the points say (shade, smell, "
                                            "width…). Give the reason.")
    result = fields.Selection(RESULTS, string="Result", compute="_compute_result", store=True, tracking=True)
    reason = fields.Char(string="Reason", tracking=True)

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "The inspection number must be unique."),
    ]

    # ------------------------------------------------------------------
    # Formulas
    # ------------------------------------------------------------------
    @api.model
    def _formula_points_per_100sqyd(self, points, yards, width_in):
        """Points per 100 sq yd = points × 3600 ÷ (inspected yards × cuttable width in inches)."""
        if yards <= 0 or width_in <= 0:
            return 0.0
        return points * 3600.0 / (yards * width_in)

    @api.model
    def _formula_penalty_points(self, defects):
        """Σ points with at most 4 points per linear yard.

        :param defects: iterable of ``(yard_position, points)``; a defect without a position (0) is not capped.
        """
        per_yard = defaultdict(int)
        loose = 0
        for yard, points in defects:
            if yard and yard > 0:
                per_yard[int(yard)] += points
            else:
                loose += points
        return loose + sum(min(4, pts) for pts in per_yard.values())

    @api.depends("defect_line_ids.points", "defect_line_ids.position_yd", "inspected_length_yd",
                 "cuttable_width_in")
    def _compute_points(self):
        for insp in self:
            lines = insp.defect_line_ids
            insp.defect_count = len(lines)
            insp.penalty_points = insp._formula_penalty_points((l.position_yd, l.points) for l in lines)
            insp.points_per_100sqyd = insp._formula_points_per_100sqyd(
                insp.penalty_points, insp.inspected_length_yd, insp.cuttable_width_in)

    @api.depends("points_per_100sqyd", "accept_limit", "result_override")
    def _compute_result(self):
        for insp in self:
            insp.result_auto = "hold" if insp.points_per_100sqyd > insp.accept_limit else "pass"
            insp.result = insp.result_override or insp.result_auto

    @api.depends("lot_id")
    def _compute_display_name(self):
        for insp in self:
            insp.display_name = " · ".join(p for p in (insp.name, insp.lot_id.name) if p)

    @api.onchange("lot_id")
    def _onchange_lot_id(self):
        lot = self.lot_id
        if lot:
            if lot.width_in and not self.cuttable_width_in:
                self.cuttable_width_in = lot.width_in
                self.width_measured_in = lot.width_in
            if lot.roll_received_qty and not self.inspected_length_yd:
                self.inspected_length_yd = lot._roll_length_yards()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            lot = self.env["stock.lot"].browse(vals.get("lot_id"))
            if lot and not vals.get("company_id"):
                vals["company_id"] = lot.company_id.id or self.env.company.id
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if "accept_limit" not in vals:
                vals["accept_limit"] = company.garment_fabric_accept_points
            if lot:
                vals.setdefault("cuttable_width_in", lot.width_in)
                vals.setdefault("width_measured_in", lot.width_in)
                vals.setdefault("inspected_length_yd", lot._roll_length_yards())
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code(
                    "garment.fabric.inspection") or _("New")
        return super().create(vals_list)

    def unlink(self):
        if any(insp.state == "done" for insp in self):
            raise UserError(_("A finished inspection cannot be deleted; reopen it first."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _default_reason(self):
        self.ensure_one()
        if self.result == "hold" and not self.result_override:
            return _("4-point score %(pts).1f over the accept limit %(limit).1f",
                     pts=self.points_per_100sqyd, limit=self.accept_limit)
        return False

    def action_done(self):
        """Finish: write the score on the roll and decide its status.
        Pass → roll approved; hold (over the limit, or held by the inspector) → roll on hold with the reason;
        reject → roll rejected."""
        for insp in self:
            if insp.state == "done":
                continue
            if insp.inspected_length_yd <= 0 or insp.cuttable_width_in <= 0:
                raise UserError(_("Enter the inspected length and the cuttable width of roll %s.",
                                  insp.lot_id.name))
            if insp.result_override and not insp.reason:
                raise UserError(_("Give the reason for holding or rejecting roll %s.", insp.lot_id.name))
            reason = insp.reason or insp._default_reason()
            insp.write({"state": "done", "reason": reason})
            lot = insp.lot_id.sudo()
            lot.write({"points_per_100sqyd": insp.points_per_100sqyd,
                       "width_cm": insp.width_measured_in * 2.54 if insp.width_measured_in else lot.width_cm,
                       "gsm": insp.gsm_measured or lot.gsm})
            if insp.result == "pass":
                if lot.roll_status in ("received", "hold"):
                    lot.action_roll_approve()
            elif insp.result == "hold":
                if lot.roll_status != "rejected":
                    lot.action_roll_hold(reason=reason)
            else:
                lot.action_roll_reject(reason=reason)
            insp.message_post(body=_("Roll %(roll)s: %(pts).1f points / 100 sq yd against %(limit).1f → %(result)s.",
                                     roll=lot.name, pts=insp.points_per_100sqyd, limit=insp.accept_limit,
                                     result=dict(RESULTS)[insp.result]))
        return True

    def action_reopen(self):
        self.write({"state": "in_progress"})
        return True

    def action_print(self):
        return self.env.ref("zyra_garment_materials.action_report_fabric_inspection").report_action(self)

    def action_open_tablet(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "zyra_fabric_inspection_tablet",
            "name": _("Fabric Inspection"),
            "params": {"inspection_id": self.id},
        }

    # ------------------------------------------------------------------
    # Tablet API (client action zyra_fabric_inspection_tablet)
    # ------------------------------------------------------------------
    @api.model
    def tablet_defect_types(self):
        defects = self.env["garment.defect"].search([("area", "=", "fabric")], order="sequence, code")
        return [{"id": d.id, "name": d.name, "code": d.code} for d in defects]

    @api.model
    def tablet_queue(self):
        """Open inspections and received rolls still waiting for one."""
        open_insp = self.search([("state", "=", "in_progress")], limit=40)
        rolls = self.env["stock.lot"].search([
            ("is_fabric_roll", "=", True), ("roll_status", "=", "received"),
            ("roll_inspection_ids", "=", False)], order="id desc", limit=40)
        return {
            "inspections": [{"id": i.id, "name": i.name, "roll": i.lot_id.name,
                             "fabric": i.product_id.name or "", "points": i.penalty_points} for i in open_insp],
            "rolls": [{"id": r.id, "name": r.name, "fabric": r.product_id.name or "",
                       "colour": r.roll_colour_label or ""} for r in rolls],
        }

    @api.model
    def tablet_start(self, lot_id):
        lot = self.env["stock.lot"].browse(lot_id).exists()
        if not lot or not lot.is_fabric_roll:
            raise UserError(_("Pick a fabric roll."))
        return self.create({"lot_id": lot.id}).id

    def tablet_state(self):
        self.ensure_one()
        last = self.defect_line_ids.sorted(lambda l: (l.sequence, l.id))[-1:]
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "frame": self.frame or "",
            "roll": self.lot_id.name,
            "colour": (self.roll_colour_label or self.product_id.name or "").upper(),
            "fabric": self.product_id.display_name or "",
            "current_yard": self.current_yard,
            "length_yd": self.inspected_length_yd,
            "width_in": self.cuttable_width_in,
            "defect_count": self.defect_count,
            "penalty_points": self.penalty_points,
            "points_per_100sqyd": round(self.points_per_100sqyd, 1),
            "accept_limit": self.accept_limit,
            "result": self.result,
            "result_label": dict(RESULTS)[self.result],
            "last_defect": last and {"name": last.defect_id.name, "band": dict(LENGTH_BANDS)[last.length_band],
                                     "yard": last.position_yd} or False,
        }

    def _check_tablet_open(self):
        if self.state != "in_progress":
            raise UserError(_("Inspection %s is finished; reopen it to change it.", self.name))

    def tablet_add_defect(self, defect_id, band, yard=None):
        self.ensure_one()
        self._check_tablet_open()
        if str(band) not in dict(LENGTH_BANDS):
            raise UserError(_("Unknown length band."))
        if yard is not None:
            self.current_yard = yard
        seq = max(self.defect_line_ids.mapped("sequence") or [0]) + 1
        self.env["garment.fabric.inspection.defect"].create({
            "inspection_id": self.id, "defect_id": defect_id or False, "length_band": str(band),
            "position_yd": self.current_yard, "sequence": seq})
        return self.tablet_state()

    def tablet_undo(self):
        self.ensure_one()
        self._check_tablet_open()
        self.defect_line_ids.sorted(lambda l: (l.sequence, l.id))[-1:].unlink()
        return self.tablet_state()

    def tablet_set(self, values):
        self.ensure_one()
        self._check_tablet_open()
        allowed = {"current_yard", "inspected_length_yd", "cuttable_width_in", "frame"}
        self.write({k: v for k, v in values.items() if k in allowed})
        return self.tablet_state()

    def tablet_finish(self):
        self.ensure_one()
        self.action_done()
        return self.tablet_state()


class GarmentFabricInspectionDefect(models.Model):
    _name = "garment.fabric.inspection.defect"
    _description = "Fabric Inspection Defect"
    _order = "inspection_id, sequence, id"

    inspection_id = fields.Many2one("garment.fabric.inspection", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="inspection_id.company_id", store=True)
    sequence = fields.Integer(default=10)
    defect_id = fields.Many2one("garment.defect", string="Defect", domain="[('area', 'in', ('fabric', 'shade'))]")
    position_yd = fields.Float(string="At Yard", digits=(16, 1))
    length_band = fields.Selection(LENGTH_BANDS, string="Length", required=True, default="1")
    points = fields.Integer(string="Points", compute="_compute_points", store=True)
    note = fields.Char(string="Note")

    @api.depends("length_band")
    def _compute_points(self):
        for line in self:
            line.points = int(line.length_band or 0)
