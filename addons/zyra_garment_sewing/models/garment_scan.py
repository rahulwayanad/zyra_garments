import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GarmentScan(models.Model):
    """One coupon scan on the sewing floor (screen 57): who sewed which operation of which bundle, the
    minutes earned (pieces × SAM) and the earnings (minutes × minute rate)."""
    _name = "garment.scan"
    _description = "Sewing Coupon Scan"
    _order = "scanned_at desc, id desc"

    coupon_id = fields.Many2one("garment.bundle.coupon", string="Coupon", required=True, ondelete="restrict",
                                index=True)
    payload = fields.Char(string="Scanned Text")
    client_uuid = fields.Char(string="Device Scan ID", index=True, copy=False,
                              help="Id given by the scan station; replaying the same id is ignored.")
    employee_id = fields.Many2one("hr.employee", string="Operator", index=True)
    line_id = fields.Many2one("garment.line", string="Line", index=True)
    bundle_id = fields.Many2one(related="coupon_id.bundle_id", store=True, index=True, string="Bundle")
    order_id = fields.Many2one(related="bundle_id.order_id", store=True, index=True, string="Order")
    company_id = fields.Many2one(related="bundle_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    operation_line_id = fields.Many2one(related="coupon_id.operation_line_id", store=True, string="Operation")
    scanned_at = fields.Datetime(string="Scanned On", required=True, default=fields.Datetime.now, index=True)
    pieces = fields.Integer(required=True)
    rejected_qty = fields.Integer(string="Rejected")
    sam = fields.Float(string="SAM", digits=(16, 3))
    minutes_earned = fields.Float(digits=(16, 2), compute="_compute_earnings", store=True)
    minute_rate = fields.Float(string="Rate / Minute", digits=(16, 4))
    earnings = fields.Monetary(compute="_compute_earnings", store=True)
    is_last_operation = fields.Boolean(string="Bundle Completed", readonly=True,
                                       help="This scan completed the bundle (it moved to sewn).")

    _sql_constraints = [
        ("coupon_once", "UNIQUE(coupon_id)", "This coupon was already scanned."),
        ("client_uuid_once", "UNIQUE(client_uuid)", "This device scan was already received."),
    ]

    @api.depends("pieces", "sam", "minute_rate")
    def _compute_earnings(self):
        for scan in self:
            scan.minutes_earned = scan.pieces * scan.sam
            scan.earnings = scan.minutes_earned * scan.minute_rate

    @api.model
    def _garment_minute_rate(self, bundle, operation):
        """Rate per minute: bulletin piece rate ÷ SAM when the style has a bulletin line for the operation,
        else the company minute rate (system parameter ``zyra_garment_sewing.minute_rate``)."""
        line = self.env["garment.bulletin.line"].search([
            ("bulletin_id.style_id", "=", bundle.style_id.id), ("operation_line_id", "=", operation.id),
            ("bulletin_id.active", "=", True)], limit=1)
        if line and line.sam and line.piece_rate:
            return line.piece_rate / line.sam
        return float(self.env["ir.config_parameter"].sudo().get_param("zyra_garment_sewing.minute_rate", 0) or 0)

    @api.model
    def _garment_scan(self, payload, employee, line=None, client_uuid=None, scanned_at=None, rejected=0,
                      reason=None):
        """Record one coupon scan. Raises ``UserError`` with an operator sentence (bad coupon, already scanned).
        When the scan completes the bundle, posts 'sewn' progress on the order."""
        if client_uuid:
            done = self.search([("client_uuid", "=", client_uuid)], limit=1)
            if done:
                return done
        employee = employee if isinstance(employee, models.BaseModel) else self.env["hr.employee"].browse(employee)
        if not employee.exists():
            raise UserError(_("Scan your badge first."))
        coupon = self.env["garment.bundle"]._garment_coupon_from_payload(payload)
        bundle, operation = coupon.bundle_id, coupon.operation_line_id
        if coupon.scanned or self.search_count([("coupon_id", "=", coupon.id)]):
            raise UserError(_("Coupon %(op)s of bundle %(bundle)s was already scanned by %(who)s.",
                              op=operation.name, bundle=bundle.name, who=coupon.employee_id.name or _("someone")))
        if line is not None and not isinstance(line, models.BaseModel):
            line = self.env["garment.line"].browse(line)
        line = line or self.env["garment.line"]._garment_from_workcenter(bundle.line_id)
        try:
            completed = coupon._garment_record_scan(employee=employee, rejected=rejected,
                                                    scanned_at=scanned_at, reason=reason)
        except ValidationError as err:
            raise UserError(str(err)) from err
        scan = self.sudo().create({
            "coupon_id": coupon.id, "payload": payload, "client_uuid": client_uuid or False,
            "employee_id": employee.id, "line_id": line.id or False, "scanned_at": coupon.scanned_at,
            "pieces": coupon.pieces, "rejected_qty": rejected, "sam": operation.sam,
            "minute_rate": self._garment_minute_rate(bundle, operation), "is_last_operation": completed,
        })
        if completed:
            bundle.flush_recordset()
            good = bundle.good_pieces if bundle.good_pieces else bundle.pieces
            if good:
                bundle.order_id._garment_add_progress("sewn", bundle.colour_id, bundle.size_id, good,
                                                      ref=bundle.name, date=coupon.scanned_at)
        return scan.with_env(self.env)

    @api.model
    def garment_sync_batch(self, items):
        """Replay a queue of offline scans from the scan station (IndexedDB queue).

        ``items``: list of dicts ``{uuid, payload, employee_id, line_id, scanned_at, rejected}``.
        Idempotent: an item whose ``uuid`` was already received is answered ``duplicate`` and changes nothing,
        so a station may resend the whole queue after a dropped connection.
        Returns a list ``{uuid, status: ok|duplicate|error, message, scan_id}`` in the same order."""
        results = []
        for item in items or []:
            uuid = item.get("uuid")
            if uuid and self.search_count([("client_uuid", "=", uuid)]):
                results.append({"uuid": uuid, "status": "duplicate", "message": "", "scan_id": False})
                continue
            try:
                with self.env.cr.savepoint():
                    scan = self._garment_scan(
                        item.get("payload"), item.get("employee_id"), line=item.get("line_id") or None,
                        client_uuid=uuid, scanned_at=item.get("scanned_at") or None,
                        rejected=int(item.get("rejected") or 0))
                results.append({"uuid": uuid, "status": "ok", "message": "", "scan_id": scan.id})
            except (UserError, ValidationError) as err:
                results.append({"uuid": uuid, "status": "error", "message": str(err), "scan_id": False})
        return results

    # ------------------------------------------------------------------
    # Scan station (screen 4)
    # ------------------------------------------------------------------
    @api.model
    def station_lines(self):
        return [{"id": line.id, "name": line.name} for line in self.env["garment.line"].search([])]

    @api.model
    def station_badge(self, code):
        """Find the operator of a badge: employee barcode, then badge id, then exact name."""
        code = (code or "").strip()
        Employee = self.env["hr.employee"].sudo()
        employee = Employee.search([("barcode", "=", code)], limit=1) if code else Employee
        if not employee and code:
            employee = Employee.search([("name", "=ilike", code)], limit=1)
        if not employee:
            raise UserError(_("Badge %s is not known.", code))
        return {"id": employee.id, "name": employee.name, "badge": employee.barcode or ""}

    @api.model
    def station_stats(self, employee_id, line_id=False):
        """Figures of the operator today: pieces, minutes earned, efficiency, earnings, last scan.
        Rule: efficiency = minutes earned ÷ minutes worked since the line's first hour (08:00) × 100;
        target so far = minutes worked × line target efficiency ÷ SAM of the operator's last operation."""
        line = self.env["garment.line"].browse(line_id).exists()
        now = fields.Datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        scans = self.search([("employee_id", "=", employee_id), ("scanned_at", ">=", start)])
        shift_start = start.replace(hour=8)
        worked = max(min((now - shift_start).total_seconds() / 60, line.working_minutes or 480), 0)
        minutes = sum(scans.mapped("minutes_earned"))
        last = scans[:1]
        target_eff = line.target_efficiency or 65.0
        currency = self.env.company.currency_id
        return {
            "line": line.name or "",
            "pieces": sum(scans.mapped("pieces")),
            "target_so_far": int(worked * target_eff / 100 / last.sam) if last.sam else 0,
            "minutes": round(minutes, 1),
            "efficiency": round(minutes / worked * 100) if worked else 0,
            "earnings": round(sum(scans.mapped("earnings")), 2),
            "currency": currency.symbol or "",
            "operation": last.operation_line_id.name or "",
            "last": last and {
                "bundle": last.bundle_id.name, "seq": last.operation_line_id.sequence,
                "operation": last.operation_line_id.name, "pieces": last.pieces,
                "minutes": round(last.minutes_earned, 1), "earnings": round(last.earnings, 2),
            } or False,
        }
