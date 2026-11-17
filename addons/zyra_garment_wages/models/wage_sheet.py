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
    rate_card_id = fields.Many2one("garment.rate.card", required=True)
    date_from = fields.Date(required=True, default=lambda s: fields.Date.today() - timedelta(days=6))
    date_to = fields.Date(required=True, default=fields.Date.today)
    state = fields.Selection([("draft", "Draft"), ("computed", "Computed"), ("posted", "Posted"),
                              ("cancel", "Cancelled")], default="draft", tracking=True, copy=False)
    line_ids = fields.One2many("garment.wage.sheet.line", "sheet_id", string="Operators", copy=False)
    journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'general')]",
                                 default=lambda s: s.env["account.journal"].search(
                                     [("type", "=", "general"), ("company_id", "=", s.env.company.id)], limit=1))
    expense_account_id = fields.Many2one("account.account", string="Wages Expense Account")
    payable_account_id = fields.Many2one("account.account", string="Wages Payable Account")
    move_id = fields.Many2one("account.move", string="Journal Entry", readonly=True, copy=False)
    operator_count = fields.Integer(compute="_compute_totals", store=True)
    total_pieces = fields.Integer(compute="_compute_totals", store=True)
    total_earnings = fields.Monetary(string="Piece Earnings", compute="_compute_totals", store=True)
    total_topup = fields.Monetary(string="Top-up", compute="_compute_totals", store=True)
    total_overtime = fields.Monetary(string="Overtime", compute="_compute_totals", store=True)
    total_incentive = fields.Monetary(string="Incentive", compute="_compute_totals", store=True)
    total_net = fields.Monetary(string="Net Payable", compute="_compute_totals", store=True)

    @api.depends("line_ids.net_payable", "line_ids.pieces")
    def _compute_totals(self):
        for sheet in self:
            ls = sheet.line_ids
            sheet.operator_count = len(ls)
            sheet.total_pieces = sum(ls.mapped("pieces"))
            sheet.total_earnings = sum(ls.mapped("piece_earnings"))
            sheet.total_topup = sum(ls.mapped("topup"))
            sheet.total_overtime = sum(ls.mapped("overtime_pay"))
            sheet.total_incentive = sum(ls.mapped("incentive"))
            sheet.total_net = sum(ls.mapped("net_payable"))

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
                raise UserError(self.env._("Only a draft wage sheet can be computed."))
            overtime = {l.employee_id.id: l.overtime_hours for l in sheet.line_ids}
            sheet.line_ids.scan_ids.sudo().write({"wage_line_id": False})
            sheet.line_ids.unlink()
            scans = self.env["garment.scan"].sudo().search(sheet._garment_scan_domain())
            by_emp = {}
            for scan in scans:
                by_emp.setdefault(scan.employee_id, self.env["garment.scan"].sudo())
                by_emp[scan.employee_id] |= scan
            for emp, emp_scans in by_emp.items():
                line = self.env["garment.wage.sheet.line"].create({
                    "sheet_id": sheet.id, "employee_id": emp.id,
                    "overtime_hours": overtime.get(emp.id, 0.0),
                })
                emp_scans.write({"wage_line_id": line.id})
            sheet.line_ids.invalidate_recordset()
            sheet.state = "computed"
        return True

    def action_post(self):
        for sheet in self:
            if sheet.state != "computed":
                raise UserError(self.env._("Compute the wage sheet before posting."))
            if not (sheet.journal_id and sheet.expense_account_id and sheet.payable_account_id):
                raise UserError(self.env._("Set the journal, wages expense and wages payable accounts."))
            lines = []
            for wl in sheet.line_ids.filtered(lambda l: not l.currency_id.is_zero(l.net_payable)):
                label = "%s · %s" % (sheet.name, wl.employee_id.name)
                partner = wl.employee_id.work_contact_id.id
                lines.append(Command.create({"name": label, "account_id": sheet.expense_account_id.id,
                                             "debit": wl.net_payable, "credit": 0.0, "partner_id": partner}))
                lines.append(Command.create({"name": label, "account_id": sheet.payable_account_id.id,
                                             "debit": 0.0, "credit": wl.net_payable, "partner_id": partner}))
            if not lines:
                raise UserError(self.env._("Nothing to pay on this wage sheet."))
            move = self.env["account.move"].create({
                "move_type": "entry", "journal_id": sheet.journal_id.id, "date": sheet.date_to,
                "ref": sheet.name, "line_ids": lines,
            })
            move.action_post()
            sheet.write({"move_id": move.id, "state": "posted"})
        return True

    def action_reset(self):
        for sheet in self:
            if sheet.move_id:
                raise UserError(self.env._("Reverse the journal entry first; a posted sheet stays posted."))
            sheet.line_ids.scan_ids.sudo().write({"wage_line_id": False})
            sheet.line_ids.unlink()
            sheet.state = "draft"
        return True

    def unlink(self):
        if any(s.state == "posted" for s in self):
            raise UserError(self.env._("A posted wage sheet cannot be deleted."))
        self.line_ids.scan_ids.sudo().write({"wage_line_id": False})
        return super().unlink()


class GarmentWageSheetLine(models.Model):
    _name = "garment.wage.sheet.line"
    _description = "Wage Sheet Operator Line"
    _order = "employee_id"

    sheet_id = fields.Many2one("garment.wage.sheet", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="sheet_id.currency_id")
    employee_id = fields.Many2one("hr.employee", string="Operator", required=True)
    scan_ids = fields.One2many("garment.scan", "wage_line_id", string="Scans", readonly=True)
    pieces = fields.Integer(compute="_compute_wage", store=True)
    minutes_earned = fields.Float(compute="_compute_wage", store=True, digits=(16, 2))
    days = fields.Integer(string="Days Worked", compute="_compute_wage", store=True)
    efficiency = fields.Float(string="Efficiency %", compute="_compute_wage", store=True, digits=(16, 1))
    overtime_hours = fields.Float(string="OT Hours")
    deduction = fields.Monetary()
    piece_earnings = fields.Monetary(compute="_compute_wage", store=True)
    minimum_wage = fields.Monetary(string="Statutory Minimum", compute="_compute_wage", store=True)
    topup = fields.Monetary(string="Top-up", compute="_compute_wage", store=True)
    overtime_pay = fields.Monetary(string="Overtime", compute="_compute_wage", store=True)
    incentive = fields.Monetary(compute="_compute_wage", store=True)
    net_payable = fields.Monetary(string="Net Payable", compute="_compute_wage", store=True)

    @api.model
    def _garment_wage_figures(self, card, minutes, days, overtime_hours=0.0, deduction=0.0):
        """Pure wage rules. Earnings are minutes × the rate card's minute value."""
        earnings = minutes * card.minute_value
        available = days * card.hours_per_day * 60
        efficiency = minutes / available * 100 if available else 0.0
        minimum = days * card.min_daily_wage
        topup = max(0.0, minimum - earnings)
        hourly_min = card.min_daily_wage / card.hours_per_day if card.hours_per_day else 0.0
        overtime = overtime_hours * hourly_min * card.overtime_multiplier
        incentive = earnings * card.incentive_percent / 100 if efficiency > card.incentive_threshold else 0.0
        net = earnings + topup + overtime + incentive - deduction
        return {"piece_earnings": earnings, "efficiency": efficiency, "minimum_wage": minimum, "topup": topup,
                "overtime_pay": overtime, "incentive": incentive, "net_payable": net}

    @api.depends("scan_ids.minutes_earned", "scan_ids.pieces", "overtime_hours", "deduction",
                 "sheet_id.rate_card_id")
    def _compute_wage(self):
        for line in self:
            scans = line.scan_ids
            minutes = sum(scans.mapped("minutes_earned"))
            days = len({fields.Datetime.to_datetime(s.scanned_at).date() for s in scans})
            line.pieces = sum(scans.mapped("pieces"))
            line.minutes_earned = minutes
            line.days = days
            line.update(self._garment_wage_figures(line.sheet_id.rate_card_id, minutes, days,
                                                   line.overtime_hours, line.deduction))
