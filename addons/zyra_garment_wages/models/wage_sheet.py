from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class GarmentWageSheet(models.Model):
    _name = "garment.wage.sheet"
    _description = "Weekly Wage Sheet"
    _inherit = ["mail.thread"]
    _order = "date_from desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_id = fields.Many2one("garment.line", string="Sewing Line",
                              help="Empty = whole floor (every line).")
    rate_card_id = fields.Many2one("garment.rate.card", string="Rate Card", required=True,
                                   domain="[('state', '=', 'active')]")
    date_from = fields.Date(string="From", required=True,
                            default=lambda s: fields.Date.today() - timedelta(days=fields.Date.today().weekday()))
    date_to = fields.Date(string="To", required=True,
                          default=lambda s: fields.Date.today() - timedelta(days=fields.Date.today().weekday()) + timedelta(days=5))
    period_label = fields.Char(string="Period and Scope", compute="_compute_period_label", store=True)
    state = fields.Selection([("draft", "Draft"), ("computed", "Computed"), ("approved", "Approved"),
                              ("posted", "Posted"), ("cancel", "Cancelled")],
                             default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("garment.wage.sheet.line", "sheet_id", string="Wage Lines", copy=False)
    note = fields.Html(string="Notes")
    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'general')]",
                                 default=lambda s: s.env["account.journal"].search(
                                     [("type", "=", "general"), ("company_id", "=", s.env.company.id)], limit=1))
    expense_account_id = fields.Many2one("account.account", string="Wages Expense Account")
    payable_account_id = fields.Many2one("account.account", string="Wages Payable Account")
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    scan_count = fields.Integer(string="Scans Paid", compute="_compute_scan_count")
    move_count = fields.Integer(string="Journal Entry", compute="_compute_scan_count")
    operator_count = fields.Integer(string="Operators", compute="_compute_totals", store=True)
    below_minimum_count = fields.Integer(string="Below Minimum", compute="_compute_totals", store=True)
    total_pieces = fields.Integer(string="Pieces", compute="_compute_totals", store=True)
    total_earnings = fields.Monetary(string="Piece Earnings", compute="_compute_totals", store=True)
    total_topup = fields.Monetary(string="Minimum Top-up", compute="_compute_totals", store=True)
    total_overtime = fields.Monetary(string="Overtime", compute="_compute_totals", store=True)
    total_incentive = fields.Monetary(string="Incentive", compute="_compute_totals", store=True)
    total_net = fields.Monetary(string="Net Payable", compute="_compute_totals", store=True)

    @api.depends("date_from", "line_id")
    def _compute_period_label(self):
        for sheet in self:
            week = sheet.date_from.isocalendar()[1] if sheet.date_from else 0
            scope = sheet.line_id.name.split(" · ")[0] if sheet.line_id else self.env._("whole floor")
            sheet.period_label = self.env._("Week %(week)s · %(scope)s", week=week, scope=scope)

    @api.depends("line_ids.net_payable", "line_ids.pieces", "line_ids.topup")
    def _compute_totals(self):
        for sheet in self:
            ls = sheet.line_ids
            sheet.operator_count = len(ls)
            sheet.below_minimum_count = len(ls.filtered(lambda l: l.topup > 0))
            sheet.total_pieces = sum(ls.mapped("pieces"))
            sheet.total_earnings = sum(ls.mapped("piece_earnings"))
            sheet.total_topup = sum(ls.mapped("topup"))
            sheet.total_overtime = sum(ls.mapped("overtime_pay"))
            sheet.total_incentive = sum(ls.mapped("incentive"))
            sheet.total_net = sum(ls.mapped("net_payable"))

    def _compute_scan_count(self):
        for sheet in self:
            sheet.scan_count = len(sheet.line_ids.scan_ids)
            sheet.move_count = 1 if sheet.move_id else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.wage.sheet") or "New"
        return super().create(vals_list)

    def _garment_scan_domain(self):
        self.ensure_one()
        start = datetime.combine(self.date_from, time.min)
        end = datetime.combine(self.date_to + timedelta(days=1), time.min)
        domain = [("scanned_at", ">=", start), ("scanned_at", "<", end),
                  ("employee_id", "!=", False), ("wage_line_id", "=", False)]
        if self.line_id:
            domain.append(("line_id", "=", self.line_id.id))
        return domain

    def action_compute(self):
        """Group unclaimed scans of the period by operator. A scan belongs to one wage line only,
        so recomputing or a second sheet never counts it twice."""
        for sheet in self:
            if sheet.state not in ("draft", "computed"):
                raise UserError(self.env._("Only a draft or computed wage sheet can be computed."))
            if sheet.date_to < sheet.date_from:
                raise UserError(self.env._("The period ends before it starts."))
            kept = {l.employee_id.id: (l.overtime_hours, l.deduction) for l in sheet.line_ids}
            sheet.line_ids.scan_ids.sudo().write({"wage_line_id": False})
            sheet.line_ids.unlink()
            scans = self.env["garment.scan"].sudo().search(sheet._garment_scan_domain(), order="scanned_at, id")
            by_emp = defaultdict(lambda: self.env["garment.scan"].sudo())
            for scan in scans:
                by_emp[scan.employee_id] |= scan
            for emp, emp_scans in sorted(by_emp.items(), key=lambda kv: (kv[0].barcode or "", kv[0].name)):
                overtime, deduction = kept.get(emp.id, (0.0, 0.0))
                line = self.env["garment.wage.sheet.line"].create({
                    "sheet_id": sheet.id, "employee_id": emp.id,
                    "paid_by": emp.sudo().garment_paid_by or "piece",
                    "overtime_hours": overtime, "deduction": deduction,
                })
                emp_scans.write({"wage_line_id": line.id})
            sheet.line_ids.invalidate_recordset()
            sheet.state = "computed"
        return True

    def action_approve(self):
        for sheet in self:
            if sheet.state != "computed":
                raise UserError(self.env._("Compute the wage sheet before approving it."))
            if not sheet.line_ids:
                raise UserError(self.env._("Nothing to pay on this wage sheet."))
        self.write({"state": "approved", "approved_by_id": self.env.uid, "approved_on": fields.Datetime.now()})
        return True

    def action_post(self):
        for sheet in self:
            if sheet.state != "approved":
                raise UserError(self.env._("Approve the wage sheet before posting."))
            if not (sheet.journal_id and sheet.expense_account_id and sheet.payable_account_id):
                raise UserError(self.env._("Set the journal, wages expense and wages payable accounts."))
            lines = []
            for wl in sheet.line_ids.filtered(lambda l: not l.currency_id.is_zero(l.net_payable)):
                label = "%s · %s" % (sheet.name, wl.employee_id.name)
                partner = wl.employee_id.sudo().work_contact_id.id
                lines.append(Command.create({"name": label, "account_id": sheet.expense_account_id.id,
                                             "debit": wl.net_payable, "credit": 0.0, "partner_id": partner}))
                lines.append(Command.create({"name": label, "account_id": sheet.payable_account_id.id,
                                             "debit": 0.0, "credit": wl.net_payable, "partner_id": partner}))
            if not lines:
                raise UserError(self.env._("Nothing to pay on this wage sheet."))
            move = self.env["account.move"].create({
                "move_type": "entry", "journal_id": sheet.journal_id.id, "date": sheet.date_to,
                "ref": "%s · %s" % (sheet.name, sheet.period_label), "line_ids": lines,
            })
            move.action_post()
            sheet.write({"move_id": move.id, "state": "posted"})
            sheet.message_post(body=self.env._(
                "Posted journal entry %s. The scans and attendance days paid by this sheet are now locked.",
                move.name))
        return True

    def action_cancel_posted(self):
        """Reverse the journal entry and free the scans so a corrected sheet can pay them."""
        for sheet in self:
            if sheet.state != "posted":
                raise UserError(self.env._("Only a posted wage sheet can be cancelled this way."))
            reversal = sheet.move_id._reverse_moves(
                [{"ref": self.env._("Reversal of %s", sheet.move_id.name), "date": fields.Date.context_today(sheet)}],
                cancel=True)
            sheet.line_ids.scan_ids.sudo().write({"wage_line_id": False})
            sheet.state = "cancel"
            sheet.message_post(body=self.env._("Cancelled: journal entry %(move)s reversed by %(rev)s; its scans are "
                                               "free again.", move=sheet.move_id.name, rev=reversal.name))
        return True

    def action_reset(self):
        for sheet in self:
            if sheet.state not in ("computed", "approved"):
                raise UserError(self.env._("Only a computed or approved sheet can go back to draft."))
            sheet.line_ids.scan_ids.sudo().write({"wage_line_id": False})
            sheet.line_ids.unlink()
            sheet.write({"state": "draft", "approved_by_id": False, "approved_on": False})
        return True

    def action_print_slips(self):
        self.ensure_one()
        return self.env.ref("zyra_garment_wages.action_report_wage_slip").report_action(self.line_ids)

    def action_open_scans(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": self.env._("Scans Paid"), "res_model": "garment.scan",
                "view_mode": "list,form", "domain": [("id", "in", self.line_ids.scan_ids.ids)]}

    def action_open_move(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.move_id.id,
                "view_mode": "form"}

    def unlink(self):
        if any(s.state == "posted" for s in self):
            raise UserError(self.env._("A posted wage sheet cannot be deleted; cancel it first."))
        self.line_ids.scan_ids.sudo().write({"wage_line_id": False})
        return super().unlink()

    # ------------------------------------------------------------------
    # Demo
    # ------------------------------------------------------------------
    @api.model
    def _garment_load_demo(self):
        """Demo: scan open coupons for the badge operators over three weeks, then build two posted
        whole-floor sheets and one computed Line 2 sheet (screens 77–81)."""
        card = self.env.ref("zyra_garment_wages.demo_rate_card", raise_if_not_found=False)
        lines = self.env["garment.line"].search([], order="id", limit=3)
        employees = self.env["hr.employee"].search([("barcode", "=like", "OP1%")], order="barcode")
        if not card or len(lines) < 3 or len(employees) < 6:
            return
        card.bulletin_ids = self.env["garment.bulletin"].search([])
        if card.bulletin_ids:
            card.action_apply_to_bulletins()
        Account = self.env["account.account"]
        expense = Account.search([("code", "=", "WAGEXP")], limit=1) or Account.create(
            {"name": "Wages Expense", "code": "WAGEXP", "account_type": "expense"})
        payable = Account.search([("code", "=", "WAGPAY")], limit=1) or Account.create(
            {"name": "Wages Payable", "code": "WAGPAY", "account_type": "liability_current"})
        journal = self.env["account.journal"].search([("type", "=", "general"),
                                                      ("company_id", "=", self.env.company.id)], limit=1)
        coupons = self.env["garment.bundle.coupon"].search(
            [("scanned", "=", False), ("bundle_id.stage", "in", ("issued", "in_sewing"))], order="bundle_id, sequence")
        if not coupons:
            return
        today = fields.Date.context_today(self)
        monday = today - timedelta(days=today.weekday())
        weeks = [monday - timedelta(days=14), monday - timedelta(days=7), monday]
        home = {emp: lines[i % 3] for i, emp in enumerate(employees)}
        stars = set(employees[2::4])  # a few fast operators earn above the minimum
        line2_team = [e for e in employees if home[e] == lines[1]]
        chunks = [coupons[: len(coupons) * 3 // 8], coupons[len(coupons) * 3 // 8: len(coupons) * 6 // 8],
                  coupons[len(coupons) * 6 // 8:]]
        Scan = self.env["garment.scan"]
        for week_start, chunk, team in zip(weeks, chunks, [employees, employees, line2_team]):
            days = [week_start + timedelta(days=d) for d in range(6) if week_start + timedelta(days=d) <= today]
            weight = {e: (8 if e in stars or week_start == monday else 1) for e in team}
            work_days = {e: days[:2] if (e in stars or week_start == monday) else days[: 5 + (i % 2)]
                         for i, e in enumerate(team)}
            got = Counter()
            total = sum(weight.values())
            for n, coupon in enumerate(chunk):
                emp = max(team, key=lambda e: (weight[e] * (n + 1) / total - got[e], -e.id))
                got[emp] += 1
                day = work_days[emp][got[emp] % len(work_days[emp])]
                Scan._garment_scan(coupon.payload, emp, line=home[emp],
                                   scanned_at=datetime.combine(day, time(4 + got[emp] % 8, 30)))
        for emp in employees[:2]:
            emp.garment_paid_by = "time"
        vals = {"rate_card_id": card.id, "journal_id": journal.id, "expense_account_id": expense.id,
                "payable_account_id": payable.id}
        for week_start in weeks[:2]:
            sheet = self.create(dict(vals, date_from=week_start, date_to=week_start + timedelta(days=5)))
            sheet.action_compute()
            sheet.line_ids[:4].write({"overtime_hours": 2.0})
            sheet.action_approve()
            sheet.action_post()
        current = self.create(dict(vals, date_from=monday, date_to=monday + timedelta(days=5), line_id=lines[1].id))
        current.action_compute()
        current.line_ids[:1].write({"overtime_hours": 1.5})


class GarmentWageSheetLine(models.Model):
    _name = "garment.wage.sheet.line"
    _description = "Wage Sheet Line"
    _order = "sheet_id desc, badge, employee_id"

    sheet_id = fields.Many2one("garment.wage.sheet", string="Wage Sheet", required=True, ondelete="cascade",
                               index=True)
    state = fields.Selection(related="sheet_id.state")
    currency_id = fields.Many2one(related="sheet_id.currency_id")
    employee_id = fields.Many2one("hr.employee", string="Operator", required=True)
    badge = fields.Char(related="employee_id.barcode", string="Badge", store=True)
    department_id = fields.Many2one(related="employee_id.department_id")
    garment_line_id = fields.Many2one("garment.line", string="Line", compute="_compute_wage", store=True)
    paid_by = fields.Selection([("piece", "Piece rate"), ("time", "Time rate")], string="Paid By",
                               default="piece", required=True)
    scan_ids = fields.One2many("garment.scan", "wage_line_id", string="Scans", readonly=True)
    pieces = fields.Integer(compute="_compute_wage", store=True)
    minutes_earned = fields.Float(string="Minutes", compute="_compute_wage", store=True, digits=(16, 1))
    days = fields.Float(string="Days", compute="_compute_wage", store=True, digits=(16, 1))
    efficiency = fields.Float(string="Efficiency %", compute="_compute_wage", store=True, digits=(16, 1))
    efficiency_ratio = fields.Float(string="Efficiency", compute="_compute_wage", store=True, digits=(16, 3))
    overtime_hours = fields.Float(string="OT Hours")
    deduction = fields.Monetary()
    piece_earnings = fields.Monetary(compute="_compute_wage", store=True)
    minimum_wage = fields.Monetary(string="Minimum", compute="_compute_wage", store=True)
    topup = fields.Monetary(string="Top-up", compute="_compute_wage", store=True)
    overtime_pay = fields.Monetary(string="Overtime", compute="_compute_wage", store=True)
    incentive = fields.Monetary(compute="_compute_wage", store=True)
    net_payable = fields.Monetary(string="Net Pay", compute="_compute_wage", store=True)

    @api.model
    def _garment_wage_figures(self, card, day_minutes, overtime_hours=0.0, deduction=0.0, paid_by="piece"):
        """Wage rules for one operator. ``day_minutes``: earned minutes per day attended.

        - piece earnings = minutes × value of a standard minute;
        - efficiency = minutes ÷ (days × hours per day × 60) × 100;
        - top-up: weekly = max(0, days × minimum − earnings); daily = Σ max(0, minimum − day earnings);
          a time-rate operator is always topped up weekly;
        - overtime = hours × (minimum ÷ hours per day) × overtime rate;
        - incentive = earnings × incentive % when efficiency is above the threshold (piece rate only);
        - net = earnings + top-up + overtime + incentive − deduction."""
        if isinstance(day_minutes, (int, float)):
            day_minutes = [day_minutes]
        day_minutes = list(day_minutes)
        days = len(day_minutes)
        minutes = sum(day_minutes)
        rate = card.minute_value
        earnings = minutes * rate
        available = days * card.hours_per_day * 60
        efficiency = minutes / available * 100 if available else 0.0
        minimum = days * card.min_daily_wage
        if card.topup_period == "daily" and paid_by == "piece":
            topup = sum(max(0.0, card.min_daily_wage - m * rate) for m in day_minutes)
        else:
            topup = max(0.0, minimum - earnings)
        hourly_min = card.min_daily_wage / card.hours_per_day if card.hours_per_day else 0.0
        overtime = overtime_hours * hourly_min * card.overtime_multiplier
        incentive = 0.0
        if paid_by == "piece" and efficiency > card.incentive_threshold:
            incentive = earnings * card.incentive_percent / 100
        net = earnings + topup + overtime + incentive - deduction
        return {"piece_earnings": earnings, "efficiency": efficiency, "efficiency_ratio": efficiency / 100,
                "minimum_wage": minimum, "topup": topup, "overtime_pay": overtime, "incentive": incentive,
                "net_payable": net, "days": float(days), "minutes_earned": minutes}

    @api.depends("scan_ids.minutes_earned", "scan_ids.pieces", "scan_ids.line_id", "overtime_hours", "deduction",
                 "paid_by", "sheet_id.rate_card_id")
    def _compute_wage(self):
        for line in self:
            scans = line.scan_ids
            per_day = defaultdict(float)
            for scan in scans:
                per_day[fields.Datetime.to_datetime(scan.scanned_at).date()] += scan.minutes_earned
            line.pieces = sum(scans.mapped("pieces"))
            counts = Counter(scans.mapped("line_id"))
            line.garment_line_id = counts.most_common(1)[0][0] if counts else False
            line.update(self._garment_wage_figures(line.sheet_id.rate_card_id, [per_day[d] for d in sorted(per_day)],
                                                   line.overtime_hours, line.deduction, line.paid_by))

    def _garment_work_done(self):
        """Rows of the wage slip: scans grouped by order and operation."""
        self.ensure_one()
        rows = {}
        rate = self.sheet_id.rate_card_id.minute_value
        for scan in self.scan_ids.sorted(lambda s: (s.order_id.name or "", s.operation_line_id.sequence)):
            key = (scan.order_id.id, scan.operation_line_id.id)
            row = rows.setdefault(key, {"order": scan.order_id.name or "", "operation": scan.operation_line_id.name,
                                        "pieces": 0, "sam": scan.sam, "minutes": 0.0, "earnings": 0.0})
            row["pieces"] += scan.pieces
            row["minutes"] += scan.minutes_earned
            row["earnings"] += scan.minutes_earned * rate
        return list(rows.values())

    def write(self, vals):
        if set(vals) - {"scan_ids"} and any(l.sheet_id.state in ("approved", "posted", "cancel") for l in self):
            raise UserError(self.env._("An approved or posted wage sheet cannot be changed."))
        return super().write(vals)
