import base64
import hashlib
import hmac
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

BUNDLE_STAGES = [
    ("cut", "Cut"),
    ("issued", "Issued to line"),
    ("in_sewing", "In sewing"),
    ("sewn", "Sewn"),
    ("finished", "Finished"),
]
BOARD_COLUMNS = [
    ("cut", "Cut"),
    ("issued", "Issued to line"),
    ("in_sewing", "In sewing"),
    ("sewn_finished", "Sewn and finished"),
]

# Coupon payload contract (see README "Coupon payload"): ZG1|<bundle id>|<operation line id>|<check>
COUPON_VERSION = "ZG1"
COUPON_SEPARATOR = "|"


class GarmentBundle(models.Model):
    """A bundle: cut pieces of one size, one colourway and one roll (so one shade) that travel together.
    It carries one coupon per sewing operation of the order's tech pack."""

    _name = "garment.bundle"
    _description = "Bundle"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Bundle", default="/", readonly=True, copy=False, index=True)
    lay_id = fields.Many2one("garment.lay", string="Lay", required=True, ondelete="restrict", index=True,
                             check_company=True)
    plan_id = fields.Many2one(related="lay_id.plan_id", store=True, string="Cut Plan")
    company_id = fields.Many2one(related="lay_id.company_id", store=True, index=True)
    order_id = fields.Many2one(related="lay_id.order_id", store=True, index=True, string="Order")
    style_id = fields.Many2one(related="lay_id.style_id", store=True)
    colour_id = fields.Many2one(related="lay_id.colour_id", store=True, string="Colourway")
    size_id = fields.Many2one("garment.size", required=True, string="Size")
    bundle_no = fields.Integer(string="Bundle No.", help="Number of the bundle within its lay.")
    roll_id = fields.Many2one("stock.lot", string="Roll", ondelete="restrict")
    shade = fields.Char(related="roll_id.shade_group", store=True, string="Shade")
    ply_from = fields.Integer(required=True, default=1)
    ply_to = fields.Integer(required=True, default=1)
    plies_label = fields.Char(string="Plies", compute="_compute_plies_label")
    pieces = fields.Integer(compute="_compute_pieces", store=True)
    stage = fields.Selection(BUNDLE_STAGES, default="cut", required=True, tracking=True, copy=False,
                             group_expand="_expand_stages")
    board_column = fields.Selection(BOARD_COLUMNS, compute="_compute_board_column", store=True,
                                    group_expand="_expand_board_columns", string="Board Column")
    line_id = fields.Many2one("mrp.workcenter", string="Line", tracking=True)
    issue_date = fields.Datetime(string="Issued On", readonly=True, copy=False)
    user_id = fields.Many2one("res.users", string="Responsible", default=lambda self: self.env.user)

    coupon_ids = fields.One2many("garment.bundle.coupon", "bundle_id", string="Coupons", copy=False)
    operation_count = fields.Integer(string="Operations", compute="_compute_scan_figures", store=True)
    operations_scanned = fields.Integer(string="Operations Scanned", compute="_compute_scan_figures", store=True)
    rejected_qty = fields.Integer(string="Rejected", compute="_compute_scan_figures", store=True)
    good_pieces = fields.Integer(string="Good Pieces", compute="_compute_scan_figures", store=True)
    progress_label = fields.Char(compute="_compute_progress_label")
    title = fields.Char(compute="_compute_title")
    scanned_coupon_ids = fields.Many2many("garment.bundle.coupon", compute="_compute_coupon_tabs",
                                          string="Scanned Operations")
    rejected_coupon_ids = fields.Many2many("garment.bundle.coupon", compute="_compute_coupon_tabs",
                                           string="Rejections")

    _sql_constraints = [
        ("ply_range", "CHECK(ply_from > 0 AND ply_to >= ply_from)", "A bundle needs a valid ply range."),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _expand_stages(self, stages, domain):
        return [key for key, _label in BUNDLE_STAGES]

    @api.model
    def _expand_board_columns(self, columns, domain):
        return [key for key, _label in BOARD_COLUMNS]

    @api.depends("ply_from", "ply_to")
    def _compute_pieces(self):
        for bundle in self:
            bundle.pieces = max(bundle.ply_to - bundle.ply_from + 1, 0)

    @api.depends("ply_from", "ply_to")
    def _compute_plies_label(self):
        for bundle in self:
            bundle.plies_label = "%s – %s" % (bundle.ply_from, bundle.ply_to)

    @api.depends("stage")
    def _compute_board_column(self):
        for bundle in self:
            bundle.board_column = "sewn_finished" if bundle.stage in ("sewn", "finished") else bundle.stage

    @api.depends("coupon_ids.scanned", "coupon_ids.rejected_qty", "pieces")
    def _compute_scan_figures(self):
        for bundle in self:
            bundle.operation_count = len(bundle.coupon_ids)
            bundle.operations_scanned = len(bundle.coupon_ids.filtered("scanned"))
            bundle.rejected_qty = sum(bundle.coupon_ids.mapped("rejected_qty"))
            bundle.good_pieces = max(bundle.pieces - bundle.rejected_qty, 0)

    @api.depends("order_id.name", "colour_id.name", "size_id.name")
    def _compute_title(self):
        for bundle in self:
            bundle.title = _("%(order)s · %(colour)s · size %(size)s", order=bundle.order_id.name or "",
                             colour=bundle.colour_id.name or "", size=bundle.size_id.name or "")

    @api.depends("coupon_ids.scanned", "coupon_ids.rejected_qty")
    def _compute_coupon_tabs(self):
        for bundle in self:
            bundle.scanned_coupon_ids = bundle.coupon_ids.filtered("scanned")
            bundle.rejected_coupon_ids = bundle.coupon_ids.filtered(lambda c: c.rejected_qty > 0)

    @api.depends("stage", "line_id", "operations_scanned", "operation_count", "good_pieces")
    def _compute_progress_label(self):
        for bundle in self:
            line = bundle.line_id.code or bundle.line_id.name or ""
            if bundle.stage == "cut":
                bundle.progress_label = _("Not issued")
            elif bundle.stage == "issued":
                bundle.progress_label = bundle.line_id.name or ""
            elif bundle.stage == "in_sewing":
                bundle.progress_label = _("%(line)s · op %(done)s of %(total)s", line=bundle.line_id.name or line,
                                          done=bundle.operations_scanned, total=bundle.operation_count)
            elif bundle.stage == "sewn":
                bundle.progress_label = _("Sewn %s", bundle.good_pieces)
            else:
                bundle.progress_label = _("Packed %s", bundle.good_pieces)

    @api.depends("name", "order_id.name", "colour_id.name", "size_id.name")
    def _compute_display_name(self):
        for bundle in self:
            bundle.display_name = bundle.name or _("New bundle")

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.bundle") or "/"
        bundles = super().create(vals_list)
        bundles._create_coupons()
        return bundles

    def unlink(self):
        if self.coupon_ids.filtered("scanned"):
            raise UserError(_("A bundle with scanned coupons cannot be deleted."))
        return super().unlink()

    def _operations(self):
        """Sewing operations of the bundle = the operation list of the order's tech pack revision."""
        self.ensure_one()
        techpack = self.order_id.techpack_id or self.style_id.current_techpack_id
        return techpack.operation_ids.sorted(lambda o: (o.sequence, o.id))

    def _create_coupons(self):
        Coupon = self.env["garment.bundle.coupon"]
        vals_list = []
        for bundle in self:
            for index, operation in enumerate(bundle._operations(), start=1):
                vals_list.append({"bundle_id": bundle.id, "sequence": index, "operation_line_id": operation.id})
        return Coupon.create(vals_list) if vals_list else Coupon

    # ------------------------------------------------------------------
    # Coupon payload — contract with zyra_garment_sewing (README "Coupon payload")
    # ------------------------------------------------------------------
    @api.model
    def _garment_coupon_check(self, bundle_id, operation_id):
        """6 upper-case hex characters: HMAC-SHA256 of 'ZG1|bundle|operation' keyed with the database secret."""
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret") or ""
        body = "%s|%d|%d" % (COUPON_VERSION, bundle_id, operation_id)
        return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:6].upper()

    def _garment_coupon_payload(self, operation):
        """Payload printed in the QR coupon of ``operation`` (a zyra.techpack.operation record or id)."""
        self.ensure_one()
        operation_id = operation.id if isinstance(operation, models.BaseModel) else int(operation)
        return COUPON_SEPARATOR.join([COUPON_VERSION, str(self.id), str(operation_id),
                                      self._garment_coupon_check(self.id, operation_id)])

    @api.model
    def _garment_parse_coupon(self, payload):
        """Read a scanned coupon. Returns ``(bundle, operation)`` — a ``garment.bundle`` and the
        ``zyra.techpack.operation`` line — or raises ``UserError`` with a sentence for the operator."""
        text = (payload or "").strip()
        parts = text.split(COUPON_SEPARATOR)
        if len(parts) != 4:
            raise UserError(_("This is not a bundle coupon: %s", text[:40]))
        version, bundle_part, operation_part, check = parts
        if version != COUPON_VERSION:
            raise UserError(_("Coupon format %s is not supported; reprint the bundle ticket.", version[:10]))
        if not (bundle_part.isdigit() and operation_part.isdigit()):
            raise UserError(_("This is not a bundle coupon: %s", text[:40]))
        bundle_id, operation_id = int(bundle_part), int(operation_part)
        if not hmac.compare_digest(check.upper(), self._garment_coupon_check(bundle_id, operation_id)):
            raise UserError(_("Coupon check failed; the coupon is damaged or was not printed here."))
        bundle = self.browse(bundle_id).exists()
        if not bundle:
            raise UserError(_("Bundle of this coupon no longer exists."))
        coupon = bundle.coupon_ids.filtered(lambda c: c.operation_line_id.id == operation_id)
        if not coupon:
            raise UserError(_("Operation of this coupon is not on bundle %s.", bundle.name))
        return bundle, coupon.operation_line_id

    @api.model
    def _garment_coupon_from_payload(self, payload):
        """Same as :meth:`_garment_parse_coupon` but returns the ``garment.bundle.coupon`` record."""
        bundle, operation = self._garment_parse_coupon(payload)
        return bundle.coupon_ids.filtered(lambda c: c.operation_line_id == operation)[:1]

    @api.model
    def _garment_qr_src(self, value, size=120):
        """Data URI of a QR code for the ticket: Odoo's report barcode (PNG); when the server's reportlab has
        no PNG renderer, the same reportlab QR drawing rendered as SVG."""
        if not value:
            return ""
        try:
            png = self.env["ir.actions.report"].barcode("QR", value, width=size, height=size)
            return "data:image/png;base64,%s" % base64.b64encode(png).decode()
        except Exception:  # noqa: BLE001 - missing renderPM backend on this server
            from reportlab.graphics import renderSVG
            from reportlab.graphics.barcode import createBarcodeDrawing
            drawing = createBarcodeDrawing("QR", value=value, width=size, height=size, barBorder=0)
            svg = renderSVG.drawToString(drawing)
            svg = svg.encode() if isinstance(svg, str) else svg
            return "data:image/svg+xml;base64,%s" % base64.b64encode(svg).decode()

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def action_issue(self, line, date=None):
        line = line if isinstance(line, models.BaseModel) else self.env["mrp.workcenter"].browse(line)
        if not line:
            raise UserError(_("Choose the sewing line the bundles go to."))
        for bundle in self:
            if bundle.stage != "cut":
                raise UserError(_("Bundle %s was already issued.", bundle.name))
        self.write({"stage": "issued", "line_id": line.id, "issue_date": date or fields.Datetime.now()})
        return True

    def action_start_sewing(self):
        for bundle in self:
            if bundle.stage not in ("cut", "issued"):
                raise UserError(_("Bundle %s is already on the line.", bundle.name))
            if not bundle.line_id:
                raise UserError(_("Issue bundle %s to a line first.", bundle.name))
            bundle.stage = "in_sewing"
        return True

    def action_mark_sewn(self):
        for bundle in self:
            if bundle.stage not in ("issued", "in_sewing"):
                raise UserError(_("Bundle %s is not on the line.", bundle.name))
            if bundle.coupon_ids.filtered(lambda c: not c.scanned):
                raise UserError(_("Bundle %s still has operations not scanned.", bundle.name))
            bundle.stage = "sewn"
        return True

    def action_finish(self):
        for bundle in self:
            if bundle.stage != "sewn":
                raise UserError(_("Only a sewn bundle can be finished."))
            bundle.stage = "finished"
        return True

    def action_reset_cut(self):
        for bundle in self:
            if bundle.stage != "issued" or bundle.coupon_ids.filtered("scanned"):
                raise UserError(_("Only an issued bundle with no scans can come back to cutting."))
        self.write({"stage": "cut", "line_id": False, "issue_date": False})
        return True

    def _split(self, pieces_new):
        """Split the last ``pieces_new`` plies into a new bundle (same lay, size, roll). Returns the new one."""
        self.ensure_one()
        if self.stage not in ("cut", "issued") or self.coupon_ids.filtered("scanned"):
            raise UserError(_("Only a bundle with no scanned operation can be split."))
        if pieces_new <= 0 or pieces_new >= self.pieces:
            raise UserError(_("The new bundle needs between 1 and %s pieces.", self.pieces - 1))
        keep_to = self.ply_to - pieces_new
        old_to = self.ply_to
        self.ply_to = keep_to
        new = self.create({
            "lay_id": self.lay_id.id, "bundle_no": self.bundle_no, "size_id": self.size_id.id,
            "roll_id": self.roll_id.id, "ply_from": keep_to + 1, "ply_to": old_to,
            "stage": self.stage, "line_id": self.line_id.id, "issue_date": self.issue_date,
        })
        self.message_post(body=_("Split: plies %(from)s – %(to)s moved to bundle %(new)s.",
                                 **{"from": keep_to + 1, "to": old_to, "new": new.name}))
        return new

    # ------------------------------------------------------------------
    def action_print_ticket(self):
        return self.env.ref("zyra_garment_cutting.action_report_bundle_ticket").report_action(self)

    def action_open_issue_wizard(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Issue Bundles to Line"),
            "res_model": "garment.bundle.issue",
            "view_mode": "form",
            "target": "new",
            "context": {"default_bundle_ids": [(6, 0, self.ids)],
                        "default_line_id": self[:1].order_id.sewing_line_id.id},
        }

    def action_open_split_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Split Bundle"),
            "res_model": "garment.bundle.split",
            "view_mode": "form",
            "target": "new",
            "context": {"default_bundle_id": self.id, "default_pieces_new": self.pieces // 2},
        }


class GarmentBundleCoupon(models.Model):
    """One tear-off coupon of a bundle ticket: one sewing operation of the bundle, scanned once."""

    _name = "garment.bundle.coupon"
    _description = "Bundle Coupon"
    _order = "bundle_id, sequence, id"

    bundle_id = fields.Many2one("garment.bundle", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="bundle_id.company_id", store=True)
    sequence = fields.Integer(string="#")
    operation_line_id = fields.Many2one("zyra.techpack.operation", string="Tech Pack Operation", required=True,
                                        ondelete="restrict", index=True)
    name = fields.Char(related="operation_line_id.name", string="Operation")
    operation_id = fields.Many2one(related="operation_line_id.operation_id", string="Library Operation")
    sam = fields.Float(related="operation_line_id.sam")
    payload = fields.Char(compute="_compute_payload", help="Text in the QR code (contract: README).")
    scanned = fields.Boolean(readonly=True, copy=False, index=True)
    employee_id = fields.Many2one("hr.employee", string="Operator", readonly=True, copy=False)
    scanned_at = fields.Datetime(string="Scanned On", readonly=True, copy=False)
    pieces = fields.Integer(string="Pieces", readonly=True, copy=False)
    rejected_qty = fields.Integer(string="Rejected", copy=False)
    reject_reason = fields.Char(copy=False)

    _sql_constraints = [
        ("operation_once", "UNIQUE(bundle_id, operation_line_id)", "A bundle has one coupon per operation."),
        ("rejected_positive", "CHECK(rejected_qty >= 0)", "Rejected pieces cannot be negative."),
    ]

    def _compute_payload(self):
        for coupon in self:
            coupon.payload = coupon.bundle_id._garment_coupon_payload(coupon.operation_line_id) \
                if coupon.bundle_id and coupon.operation_line_id else False

    @api.depends("bundle_id.name", "sequence", "name")
    def _compute_display_name(self):
        for coupon in self:
            coupon.display_name = "%s/%02d %s" % (coupon.bundle_id.name or "", coupon.sequence or 0,
                                                   coupon.name or "")

    def _garment_record_scan(self, employee=None, pieces=None, rejected=0, scanned_at=None, reason=None):
        """Mark this coupon scanned (contract for zyra_garment_sewing).

        Refuses a second scan with who scanned it. Moves the bundle to 'in_sewing' on its first scan and to
        'sewn' when every coupon is scanned. Posting 'sewn' progress on the order is left to the caller.
        Returns ``True`` when this scan completed the bundle."""
        self.ensure_one()
        if self.scanned:
            raise ValidationError(_("Coupon %(coupon)s was already scanned by %(who)s on %(when)s.",
                                    coupon=self.display_name, who=self.employee_id.name or _("someone"),
                                    when=fields.Datetime.to_string(self.scanned_at)))
        bundle = self.bundle_id
        if bundle.stage in ("sewn", "finished"):
            raise ValidationError(_("Bundle %s is already sewn.", bundle.name))
        if rejected < 0 or rejected > bundle.pieces:
            raise ValidationError(_("Rejected pieces must be between 0 and %s.", bundle.pieces))
        employee = employee if isinstance(employee, models.BaseModel) else \
            self.env["hr.employee"].browse(employee or [])
        self.sudo().write({
            "scanned": True,
            "employee_id": employee.id or False,
            "scanned_at": scanned_at or fields.Datetime.now(),
            "pieces": pieces if pieces is not None else bundle.pieces,
            "rejected_qty": rejected,
            "reject_reason": reason,
        })
        if bundle.stage in ("cut", "issued"):
            bundle.sudo().stage = "in_sewing"
        if not bundle.coupon_ids.filtered(lambda c: not c.scanned):
            bundle.sudo().stage = "sewn"
            return True
        return False
