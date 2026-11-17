from datetime import datetime, time, timedelta

from odoo import _, api, fields, models


class GarmentLine(models.Model):
    """Sewing line. Backed by an ``mrp.workcenter`` (merch decision: sewing lines are work centres), so
    ``garment.bundle.line_id`` and ``garment.order.sewing_line_id`` point at ``workcenter_id``."""
    _name = "garment.line"
    _inherits = {"mrp.workcenter": "workcenter_id"}
    _description = "Sewing Line"
    _order = "sequence, id"

    workcenter_id = fields.Many2one("mrp.workcenter", string="Work Centre", required=True, ondelete="cascade",
                                    index=True)
    supervisor_id = fields.Many2one("hr.employee", string="Supervisor")
    employee_ids = fields.Many2many("hr.employee", string="Operator List")
    operator_count = fields.Integer(string="Operators", default=20,
                                    help="Operators normally on the line (used when no operator list is kept).")
    machine_count = fields.Integer(string="Machines", default=22)
    working_minutes = fields.Integer(string="Minutes per Day", default=480)
    capacity_minutes = fields.Integer(string="Capacity (min/day)", compute="_compute_capacity", store=True,
                                      help="Operators × minutes per day.")
    target_efficiency = fields.Float(string="Target Efficiency %", default=65.0)
    current_bulletin_id = fields.Many2one("garment.bulletin", string="Running Style Bulletin")
    target_per_hour = fields.Integer(string="Target / Hour", compute="_compute_target", store=True)
    scan_ids = fields.One2many("garment.scan", "line_id", string="Scans")

    @api.depends("operator_count", "working_minutes")
    def _compute_capacity(self):
        for line in self:
            line.capacity_minutes = line.operator_count * line.working_minutes

    @api.depends("operator_count", "target_efficiency", "current_bulletin_id.total_sam")
    def _compute_target(self):
        for line in self:
            sam = line.current_bulletin_id.total_sam
            line.target_per_hour = int(round(line.operator_count * 60 * line.target_efficiency / 100 / sam, 6)) if sam else 0

    @api.model
    def _garment_from_workcenter(self, workcenter):
        if not workcenter:
            return self.browse()
        return self.search([("workcenter_id", "=", workcenter.id)], limit=1)

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------
    def _garment_day_bounds(self, day):
        day = fields.Date.to_date(day or fields.Date.context_today(self))
        start = datetime.combine(day, time.min)
        return start, start + timedelta(days=1)

    def _garment_day_scans(self, day=None):
        start, stop = self._garment_day_bounds(day)
        return self.env["garment.scan"].search([
            ("line_id", "in", self.ids), ("scanned_at", ">=", start), ("scanned_at", "<", stop)])

    def _garment_daily_summary(self, day=None):
        """Daily line summary (screen 58). Rule: efficiency = earned minutes ÷ available minutes × 100;
        available = operators × minutes per day; lost minutes = available − earned; output = pieces of
        last-operation scans; WIP days = pieces on the line ÷ output of the day."""
        self.ensure_one()
        scans = self._garment_day_scans(day)
        earned = sum(scans.mapped("minutes_earned"))
        available = self.capacity_minutes
        output = sum(scans.filtered("is_last_operation").mapped("pieces"))
        wip_bundles = self.env["garment.bundle"].search([
            ("line_id", "=", self.workcenter_id.id), ("stage", "in", ("issued", "in_sewing"))])
        wip = sum(wip_bundles.mapped("pieces"))
        dhu = False
        if "garment.inspection" in self.env and hasattr(self.env["garment.inspection"], "_garment_line_dhu"):
            dhu = self.env["garment.inspection"]._garment_line_dhu(self, day)
        return {
            "line": self.name,
            "pieces": output,
            "earned_minutes": round(earned, 2),
            "available_minutes": available,
            "efficiency": round(earned / available * 100, 1) if available else 0.0,
            "lost_minutes": round(max(available - earned, 0.0), 2),
            "wip_pieces": wip,
            "wip_days": round(wip / output, 1) if output else 0.0,
            "dhu": dhu,
            "rejected": sum(scans.mapped("rejected_qty")),
        }

    def _garment_hourly_board(self, day=None, first_hour=8, hours=9):
        """Line TV board (screen 56): output vs target hour by hour, efficiency, top operator."""
        self.ensure_one()
        scans = self._garment_day_scans(day)
        start, _stop = self._garment_day_bounds(day)
        rows = []
        for h in range(first_hour, first_hour + hours):
            h_start, h_stop = start + timedelta(hours=h), start + timedelta(hours=h + 1)
            in_hour = scans.filtered(lambda s: h_start <= s.scanned_at < h_stop)
            earned = sum(in_hour.mapped("minutes_earned"))
            rows.append({
                "hour": "%02d:00" % h,
                "output": sum(in_hour.filtered("is_last_operation").mapped("pieces")),
                "target": self.target_per_hour,
                "efficiency": round(earned / (self.operator_count * 60) * 100, 1) if self.operator_count else 0.0,
            })
        by_operator = {}
        for scan in scans.filtered("employee_id"):
            by_operator[scan.employee_id] = by_operator.get(scan.employee_id, 0.0) + scan.minutes_earned
        top = max(by_operator.items(), key=lambda kv: kv[1]) if by_operator else None
        summary = self._garment_daily_summary(day)
        return {
            "line": self.name,
            "hours": rows,
            "output": summary["pieces"],
            "target": self.target_per_hour * hours,
            "efficiency": summary["efficiency"],
            "top_operator": top and top[0].name or "",
            "top_operator_minutes": top and round(top[1], 2) or 0.0,
        }

    def action_open_scans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Scans"), "res_model": "garment.scan",
            "view_mode": "list,form", "domain": [("line_id", "=", self.id)],
        }

    # ------------------------------------------------------------------
    # Line TV board (screen 56) — public RPC entry
    # ------------------------------------------------------------------
    def garment_tv_board(self, day=None):
        """Data of the TV board: header, 4 tiles (output, efficiency, target/hour, top operator) and the
        hour-by-hour bars from :meth:`_garment_hourly_board`."""
        self.ensure_one()
        board = self._garment_hourly_board(day)
        now = fields.Datetime.now()
        done_hours = [h for h in board["hours"] if int(h["hour"][:2]) < now.hour]
        current = next((h for h in board["hours"] if int(h["hour"][:2]) == now.hour), None)
        bundle = self.env["garment.bundle"].search([("line_id", "=", self.workcenter_id.id),
                                                    ("stage", "in", ("issued", "in_sewing"))], limit=1)
        order = bundle.order_id
        top = board["top_operator"]
        top_scan = self.env["garment.scan"].search([("line_id", "=", self.id), ("employee_id.name", "=", top)],
                                                   limit=1) if top else self.env["garment.scan"]
        worked = max(len(done_hours) * 60 + (now.minute if current else 0), 1)
        board.update({
            "title": self.name,
            "subtitle": " · ".join(filter(None, [order.name, order.style_id.name,
                                                 fields.Datetime.context_timestamp(self, now).strftime("%d %b, %H:%M")])),
            "target_so_far": self.target_per_hour * len(done_hours),
            "target_efficiency": self.target_efficiency,
            "target_per_hour": self.target_per_hour,
            "this_hour": current["output"] if current else 0,
            "top_operator_pct": round(board["top_operator_minutes"] / worked * 100) if top else 0,
            "top_operator_operation": top_scan.operation_line_id.name or "",
            "current_hour": now.hour,
            "max_bar": max([self.target_per_hour] + [h["output"] for h in board["hours"]] + [1]),
        })
        return board
