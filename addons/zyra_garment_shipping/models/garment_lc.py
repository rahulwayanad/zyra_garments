from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class GarmentLc(models.Model):
    """Letter of credit opened by the buyer's bank: amount, tolerance, latest shipment date, expiry."""

    _name = "garment.lc"
    _description = "Letter of Credit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiry_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="LC No.", required=True, tracking=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one("res.currency", required=True,
                                  default=lambda self: self.env.company.currency_id)
    state = fields.Selection([("draft", "Draft"), ("open", "Open"), ("closed", "Closed")],
                             default="draft", required=True, tracking=True, index=True)
    display_state = fields.Selection(
        [("draft", "Draft"), ("open", "Open"), ("expired", "Expired"), ("closed", "Closed")],
        string="Status", compute="_compute_dates")
    buyer_id = fields.Many2one("res.partner", string="Applicant", required=True, tracking=True,
                               domain="[('is_garment_buyer', '=', True)]")
    beneficiary_id = fields.Many2one("res.partner", string="Beneficiary",
                                     default=lambda self: self.env.company.partner_id)
    issuing_bank = fields.Char(string="Issuing Bank", tracking=True)
    advising_bank = fields.Char(string="Advising Bank")
    title = fields.Char(compute="_compute_title")

    amount = fields.Monetary(string="Amount", required=True, tracking=True)
    tolerance_pct = fields.Float(string="Tolerance (%)", default=5.0, tracking=True,
                                 help="Plus or minus on amount and quantity, in percent.")
    tolerance_label = fields.Char(string="Tolerance", compute="_compute_title")
    latest_shipment_date = fields.Date(string="Latest Shipment Date", required=True, tracking=True)
    expiry_date = fields.Date(string="Expiry", required=True, tracking=True)
    partial_shipments = fields.Selection([("allowed", "Allowed"), ("not_allowed", "Not allowed")],
                                         string="Partial Shipments", default="allowed")
    documents = fields.Char(string="Documents", default=lambda self: _(
        "Invoice, packing list, B/L, certificate of origin"))

    drawing_ids = fields.One2many("garment.lc.drawing", "lc_id", string="Drawings")
    drawn = fields.Monetary(string="Drawn", compute="_compute_amounts", store=True)
    balance = fields.Monetary(string="Balance", compute="_compute_amounts", store=True)
    days_left = fields.Integer(string="Days Left", compute="_compute_dates",
                               help="Days until expiry; 0 once expired.")
    is_expired = fields.Boolean(string="Expired", compute="_compute_dates", search="_search_is_expired")
    expiry_before_shipment = fields.Boolean(compute="_compute_dates")
    latest_shipment_soon = fields.Boolean(compute="_compute_dates")
    shipment_ids = fields.One2many("garment.shipment", "lc_id", string="Shipments")
    shipment_count = fields.Integer(compute="_compute_shipment_count")
    amendment_count = fields.Integer(string="Amendments", readonly=True, copy=False)

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "An LC number is used once per company."),
        ("amount_positive", "CHECK(amount > 0)", "The credit amount must be above zero."),
        ("tolerance_range", "CHECK(tolerance_pct >= 0 AND tolerance_pct <= 100)",
         "The tolerance is a percentage between 0 and 100."),
    ]

    @api.depends("buyer_id", "issuing_bank", "tolerance_pct")
    def _compute_title(self):
        for lc in self:
            lc.title = " · ".join(p for p in (lc.buyer_id.name, lc.issuing_bank) if p)
            lc.tolerance_label = "± %s%%" % ("%g" % lc.tolerance_pct)

    @api.depends("amount", "drawing_ids.amount")
    def _compute_amounts(self):
        for lc in self:
            lc.drawn = sum(lc.drawing_ids.mapped("amount"))
            lc.balance = lc.amount - lc.drawn

    @api.depends("expiry_date", "latest_shipment_date", "state")
    def _compute_dates(self):
        today = fields.Date.context_today(self)
        for lc in self:
            lc.is_expired = bool(lc.expiry_date and lc.expiry_date < today and lc.state != "closed")
            lc.days_left = max((lc.expiry_date - today).days, 0) if lc.expiry_date else 0
            lc.expiry_before_shipment = bool(lc.expiry_date and lc.latest_shipment_date
                                             and lc.expiry_date < lc.latest_shipment_date)
            lc.latest_shipment_soon = bool(lc.latest_shipment_date
                                           and (lc.latest_shipment_date - today).days <= 14)
            lc.display_state = "expired" if lc.is_expired and lc.state == "open" else lc.state

    def _search_is_expired(self, operator, value):
        today = fields.Date.context_today(self)
        expired = [("expiry_date", "<", today), ("state", "!=", "closed")]
        if (operator == "=") == bool(value):
            return expired
        return ["|", ("expiry_date", ">=", today), ("state", "=", "closed")]

    def _compute_shipment_count(self):
        for lc in self:
            lc.shipment_count = len(lc.shipment_ids)

    @api.constrains("drawing_ids", "amount", "tolerance_pct")
    def _check_drawn_within_tolerance(self):
        for lc in self:
            limit = lc.amount * (1 + lc.tolerance_pct / 100.0)
            if float_compare(lc.drawn, limit, precision_rounding=lc.currency_id.rounding) > 0:
                raise ValidationError(_(
                    "Drawings on %(lc)s (%(drawn).2f) exceed the credit amount plus its tolerance (%(limit).2f).",
                    lc=lc.name, drawn=lc.drawn, limit=limit))

    # ------------------------------------------------------------------ chatter warnings
    def _warn_expiry_before_shipment(self):
        for lc in self.filtered("expiry_before_shipment"):
            lc.message_post(body=_("The expiry date is before the latest shipment date. "
                                   "Ask the buyer for an amendment."))

    @api.model_create_multi
    def create(self, vals_list):
        lcs = super().create(vals_list)
        lcs._warn_expiry_before_shipment()
        return lcs

    def write(self, vals):
        before = {lc.id: lc.expiry_before_shipment for lc in self}
        res = super().write(vals)
        if {"expiry_date", "latest_shipment_date"} & set(vals):
            self.filtered(lambda lc: not before.get(lc.id))._warn_expiry_before_shipment()
        return res

    # ------------------------------------------------------------------ helpers for shipments
    def _shipment_warnings(self, ship_date, value):
        """Sentences explaining why shipping ``value`` on ``ship_date`` under this credit needs a check."""
        self.ensure_one()
        warnings = []
        if self.state != "open" or (self.expiry_date and ship_date and ship_date > self.expiry_date) \
                or self.is_expired:
            warnings.append(_("Letter of credit %s is not open.", self.name))
        if ship_date and self.latest_shipment_date and ship_date > self.latest_shipment_date:
            warnings.append(_("The shipment date %(ship)s is after the latest shipment date of the credit "
                              "(%(latest)s).", ship=ship_date, latest=self.latest_shipment_date))
        limit = self.balance * (1 + self.tolerance_pct / 100.0)
        if value and float_compare(value, limit, precision_rounding=self.currency_id.rounding) > 0:
            warnings.append(_("The shipment value is above the balance of the credit plus its tolerance."))
        return warnings

    # ------------------------------------------------------------------ buttons
    def action_open(self):
        for lc in self:
            if lc.state != "draft":
                raise UserError(_("Only a draft credit can be opened."))
        self.state = "open"

    def action_close(self):
        self.state = "closed"

    def action_draft(self):
        self.state = "draft"

    def action_record_drawing(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Drawing"),
            "res_model": "garment.lc.drawing",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lc_id": self.id, "default_amount": self.balance},
        }

    def action_amend(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Amend Letter of Credit"),
            "res_model": "garment.lc.amend.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lc_id": self.id},
        }

    def action_view_shipments(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_shipping.action_garment_shipment")
        action["domain"] = [("lc_id", "=", self.id)]
        action["context"] = {"default_lc_id": self.id, "default_buyer_id": self.buyer_id.id}
        return action


class GarmentLcDrawing(models.Model):
    _name = "garment.lc.drawing"
    _description = "Letter of Credit Drawing"
    _order = "date desc, id desc"

    lc_id = fields.Many2one("garment.lc", string="Letter of Credit", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="lc_id.company_id", store=True)
    currency_id = fields.Many2one(related="lc_id.currency_id")
    date = fields.Date(required=True, default=fields.Date.context_today)
    shipment_id = fields.Many2one("garment.shipment", string="Shipment", domain="[('lc_id', '=', lc_id)]")
    amount = fields.Monetary(required=True)
    note = fields.Char()

    _sql_constraints = [
        ("amount_positive", "CHECK(amount > 0)", "A drawing is above zero."),
    ]

    @api.constrains("amount", "lc_id")
    def _check_lc_limit(self):
        self.mapped("lc_id")._check_drawn_within_tolerance()

    @api.model_create_multi
    def create(self, vals_list):
        drawings = super().create(vals_list)
        for d in drawings:
            d.lc_id.message_post(body=_("Drawing of %(amount).2f recorded%(ship)s.", amount=d.amount,
                                        ship=(" " + _("for %s", d.shipment_id.name)) if d.shipment_id else ""))
        return drawings
