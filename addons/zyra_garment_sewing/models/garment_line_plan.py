import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GarmentLinePlan(models.Model):
    """An order planned on a sewing line for a period (bar on the planning board, screen 3).
    Rule: sewing minutes = pieces left to sew × style SAM; days = minutes ÷ (line capacity minutes × target
    efficiency); a bar is late when it ends after the order's ex-factory date; bars of one line that overlap clash."""
    _name = "garment.line.plan"
    _description = "Line Plan"
    _order = "line_id, date_start, id"

    order_id = fields.Many2one("garment.order", string="Order", required=True, ondelete="cascade", index=True)
    line_id = fields.Many2one("garment.line", string="Line", required=True, index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    style_id = fields.Many2one(related="order_id.style_id")
    date_start = fields.Date(required=True, default=fields.Date.context_today)
    date_end = fields.Date(required=True)
    pieces = fields.Integer()
    minutes = fields.Float(digits=(16, 0))
    is_late = fields.Boolean(compute="_compute_flags")
    has_clash = fields.Boolean(compute="_compute_flags")

    @api.depends("date_start", "date_end", "line_id", "order_id.ex_factory_date")
    def _compute_flags(self):
        for plan in self:
            plan.is_late = bool(plan.order_id.ex_factory_date and plan.date_end
                                and plan.date_end > plan.order_id.ex_factory_date)
            plan.has_clash = bool(plan.line_id and plan.date_start and plan.date_end and self.search_count([
                ("id", "!=", plan.id or 0), ("line_id", "=", plan.line_id.id),
                ("date_start", "<=", plan.date_end), ("date_end", ">=", plan.date_start)]))

    @api.model
    def _garment_style_sam(self, style):
        bulletin = self.env["garment.bulletin"].search([("style_id", "=", style.id)], limit=1)
        if bulletin.total_sam:
            return bulletin.total_sam
        techpack = self.env["zyra.techpack"].search([("style_id", "=", style.id)], order="id desc", limit=1)
        return sum(techpack.operation_ids.mapped("sam"))

    @api.model
    def _garment_days(self, line, minutes):
        per_day = line.capacity_minutes * (line.target_efficiency or 100) / 100
        return max(1, math.ceil(minutes / per_day)) if per_day else 1

    @api.model
    def garment_plan_orders(self):
        """Put every running order with a sewing line and no plan after the line's last bar."""
        orders = self.env["garment.order"].search([
            ("state", "in", ("confirmed", "in_production")), ("sewing_line_id", "!=", False)],
            order="ex_factory_date, id")
        planned = set(self.search([]).mapped("order_id").ids)
        today = fields.Date.context_today(self)
        for order in orders.filtered(lambda o: o.id not in planned):
            line = self.env["garment.line"]._garment_from_workcenter(order.sewing_line_id)
            if not line:
                continue
            pieces = max(order.qty_ordered - order.qty_sewn, 0)
            minutes = pieces * self._garment_style_sam(order.style_id)
            last = self.search([("line_id", "=", line.id)], order="date_end desc", limit=1)
            start = max(today, last.date_end + timedelta(days=1)) if last else today
            self.create({"order_id": order.id, "line_id": line.id, "date_start": start, "pieces": pieces,
                         "minutes": minutes,
                         "date_end": start + timedelta(days=self._garment_days(line, minutes) - 1)})
        return True

    def garment_move(self, line_id, date_start):
        """Drag a bar to another line / start date; keeps its length in days."""
        self.ensure_one()
        start = fields.Date.to_date(date_start)
        length = (self.date_end - self.date_start).days
        line = self.env["garment.line"].browse(line_id).exists()
        if not line:
            raise UserError(_("Line not found."))
        self.write({"line_id": line.id, "date_start": start, "date_end": start + timedelta(days=length)})
        return True

    @api.model
    def garment_board(self, weeks=8):
        """Data of the planning board: weeks, lines with load % and bars, header KPIs."""
        today = fields.Date.context_today(self)
        start = today - timedelta(days=today.weekday())
        stop = start + timedelta(weeks=weeks) - timedelta(days=1)
        lines = self.env["garment.line"].search([])
        plans = self.search([("date_end", ">=", start), ("date_start", "<=", stop)])
        total_days = weeks * 7
        rows, loads = [], []
        for line in lines:
            line_plans = plans.filtered(lambda p: p.line_id == line)
            capacity = line.capacity_minutes * (line.target_efficiency or 100) / 100 * weeks * 6
            minutes = 0.0
            for plan in line_plans:
                days = max((plan.date_end - plan.date_start).days + 1, 1)
                inside = (min(plan.date_end, stop) - max(plan.date_start, start)).days + 1
                minutes += plan.minutes * inside / days
            load = round(minutes / capacity * 100) if capacity else 0
            if line_plans:
                loads.append(load)
            rows.append({
                "id": line.id, "name": line.name, "load": load,
                "bars": [{
                    "id": p.id, "label": " ".join(filter(None, [p.style_id.code, p.style_id.name])),
                    "order": p.order_id.name,
                    "left": max((p.date_start - start).days, 0) / total_days * 100,
                    "width": max(((min(p.date_end, stop) - max(p.date_start, start)).days + 1), 1) / total_days * 100,
                    "late": p.is_late, "clash": p.has_clash,
                    "ex_factory": p.order_id.ex_factory_date and fields.Date.to_string(p.order_id.ex_factory_date),
                    "ex_left": p.is_late and (p.order_id.ex_factory_date - start).days / total_days * 100,
                } for p in line_plans],
            })
        return {
            "start": fields.Date.to_string(start),
            "weeks": [{"label": _("Wk %s", (start + timedelta(weeks=i)).isocalendar()[1]),
                       "date": fields.Date.to_string(start + timedelta(weeks=i))} for i in range(weeks)],
            "lines": rows,
            "orders_planned": len(plans.mapped("order_id")),
            "late": len(plans.filtered("is_late").mapped("order_id")),
            "clashes": len(plans.filtered("has_clash")) // 2 + len(plans.filtered("has_clash")) % 2,
            "average_load": round(sum(loads) / len(loads)) if loads else 0,
        }
