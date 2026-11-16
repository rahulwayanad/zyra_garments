from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape
from markupsafe import Markup


class GarmentApproval(models.Model):
    """Buyer approval card: lab dip, strike-off, trim card or wash standard."""

    _name = "garment.approval"
    _description = "Buyer Approval Card"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "decision_due, id desc"
    _check_company_auto = True

    name = fields.Char(string="Card No.", required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, index=True,
                                 default=lambda self: self.env.company)
    state = fields.Selection([
        ("draft", "To Send"),
        ("resubmit", "Resubmission Asked"),
        ("with_buyer", "With the Buyer"),
        ("approved", "Approved"),
    ], default="draft", required=True, tracking=True, group_expand="_group_expand_state", index=True)
    kind = fields.Selection([
        ("lab_dip", "Lab dip"),
        ("strike_off", "Strike-off"),
        ("trim_card", "Trim card"),
        ("wash_standard", "Wash standard"),
    ], required=True, default="lab_dip", tracking=True)
    style_id = fields.Many2one("garment.style", string="Style", required=True, index=True, check_company=True)
    order_id = fields.Many2one("garment.order", string="Production Order", check_company=True,
                               domain="[('style_id', '=', style_id)]")
    colour_id = fields.Many2one("garment.colour", string="Colourway")
    colour_hex = fields.Char(related="colour_id.hex")
    material_id = fields.Many2one("product.product", string="Material")
    buyer_id = fields.Many2one("res.partner", string="Buyer", compute="_compute_buyer", store=True,
                               readonly=False, domain="[('is_garment_buyer', '=', True)]")
    merchandiser_id = fields.Many2one("res.users", string="Merchandiser", default=lambda self: self.env.user)
    option_ids = fields.One2many("garment.approval.option", "approval_id", string="Options", copy=True)
    options_sent = fields.Char(compute="_compute_options_sent")
    chosen_option_id = fields.Many2one("garment.approval.option", string="Option Approved", tracking=True,
                                       domain="[('approval_id', '=', id)]")
    swatch_html = fields.Html(compute="_compute_options_sent", sanitize=False)
    swatch_image = fields.Image(string="Swatch Photo", max_width=512, max_height=512)
    submission = fields.Integer(string="Submission No.", default=0, readonly=True, tracking=True)
    first_sent_date = fields.Date(readonly=True, copy=False)
    sent_date = fields.Date(string="Sent On", tracking=True)
    decision_due = fields.Date(string="Decision Due", tracking=True)
    decision_date = fields.Date(string="Decided On", tracking=True)
    courier = fields.Char()
    buyer_comment = fields.Text(string="Buyer Comments")
    decision_due_in = fields.Integer(string="Decision Due (days)", compute="_compute_kpis")
    decision_due_label = fields.Char(string="Decision Due In", compute="_compute_kpis")
    days_to_approval = fields.Integer(compute="_compute_kpis")
    days_to_approval_label = fields.Char(string="Days to Approval", compute="_compute_kpis")
    other_open_count = fields.Integer(string="Other Open Cards", compute="_compute_kpis")
    is_overdue = fields.Boolean(compute="_compute_kpis", search="_search_overdue")

    @api.model
    def _group_expand_state(self, states, domain):
        order = ["resubmit", "with_buyer", "approved"]
        return [s for s in ("draft",) if s in states] + order

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(
                    vals.get("company_id") or self.env.company.id).next_by_code("garment.approval") or _("New")
        return super().create(vals_list)

    @api.depends("name", "kind", "style_id.code", "colour_id.name")
    def _compute_display_name(self):
        labels = dict(self._fields["kind"]._description_selection(self.env))
        for a in self:
            a.display_name = " · ".join(
                p for p in (a.name, labels.get(a.kind), a.style_id.code, a.colour_id.name) if p)

    @api.depends("order_id.buyer_id", "style_id.buyer_id")
    def _compute_buyer(self):
        for a in self:
            a.buyer_id = a.order_id.buyer_id or a.style_id.buyer_id or a.buyer_id

    @api.depends("option_ids.name", "option_ids.hex", "colour_id.name", "colour_id.hex")
    def _compute_options_sent(self):
        for a in self:
            names = a.option_ids.mapped("name")
            if not names:
                a.options_sent = False
            else:
                listed = names[0] if len(names) == 1 else _("%(first)s and %(last)s",
                                                             first=", ".join(names[:-1]), last=names[-1])
                a.options_sent = _("%(opts)s against %(colour)s", opts=listed, colour=a.colour_id.name) \
                    if a.colour_id else listed
            hexes = [h for h in a.option_ids.mapped("hex") if h] or ([a.colour_id.hex] if a.colour_id.hex else [])
            if hexes:
                cells = Markup("").join(
                    Markup('<span style="flex:1;background:%s"></span>') % html_escape(h) for h in hexes)
                a.swatch_html = Markup(
                    '<div class="o_zyra_swatch" style="display:flex;width:84px;height:84px;'
                    'border-radius:10px;overflow:hidden;border:1px solid #e9e6f3">%s</div>') % cells
            else:
                a.swatch_html = False

    @api.depends("decision_due", "decision_date", "first_sent_date", "state", "style_id")
    def _compute_kpis(self):
        today = fields.Date.context_today(self)
        for a in self:
            if a.state in ("with_buyer", "resubmit") and a.decision_due:
                a.decision_due_in = (a.decision_due - today).days
                a.decision_due_label = _("%s d", a.decision_due_in)
            else:
                a.decision_due_in = 0
                a.decision_due_label = "—"
            if a.state == "approved" and a.decision_date and a.first_sent_date:
                a.days_to_approval = (a.decision_date - a.first_sent_date).days
                a.days_to_approval_label = _("%s d", a.days_to_approval)
            else:
                a.days_to_approval = 0
                a.days_to_approval_label = "—"
            a.is_overdue = a._is_overdue_on(today)
            if a.style_id and a.id:
                a.other_open_count = self.search_count([
                    ("style_id", "=", a.style_id.id), ("state", "!=", "approved"), ("id", "!=", a.id)])
            else:
                a.other_open_count = 0

    def _is_overdue_on(self, day):
        """Rule: a card is overdue when its decision due date has passed and it is not approved."""
        self.ensure_one()
        return bool(self.decision_due and self.decision_due < day and self.state in ("with_buyer", "resubmit"))

    def _search_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        ids = self.search([("decision_due", "<", today), ("state", "in", ["with_buyer", "resubmit"])]).ids
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", ids)]

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_send(self):
        """Send (or resend) the card to the buyer: the submission number goes up by one."""
        today = fields.Date.context_today(self)
        for a in self:
            if a.state not in ("draft", "resubmit"):
                raise UserError(_("Only a new card or one with a resubmission asked can be sent."))
            a.write({
                "state": "with_buyer",
                "submission": a.submission + 1,
                "sent_date": today,
                "first_sent_date": a.first_sent_date or today,
                "decision_date": False,
                "chosen_option_id": False,
            })

    def action_approve(self):
        for a in self:
            if a.state != "with_buyer":
                raise UserError(_("Only a card with the buyer can be approved."))
            if a.option_ids and not a.chosen_option_id:
                raise UserError(_("Record which option the buyer chose before approving %s.", a.name))
            a.write({"state": "approved", "decision_date": a.decision_date or fields.Date.context_today(a)})
            body = _("Submission %(n)s approved.", n=a.submission)
            if a.chosen_option_id:
                body = _("Submission %(n)s approved: option %(opt)s.", n=a.submission, opt=a.chosen_option_id.name)
            if a.buyer_comment:
                body += " " + _("Comment: %s", a.buyer_comment)
            a.message_post(body=body)

    def action_ask_resubmission(self):
        for a in self:
            if a.state != "with_buyer":
                raise UserError(_("Only a card with the buyer can be sent back for resubmission."))
            a.write({"state": "resubmit", "decision_date": fields.Date.context_today(a)})
            a.message_post(body=_("Submission %(n)s: buyer asked for a resubmission. %(c)s",
                                  n=a.submission, c=a.buyer_comment or ""))


class GarmentApprovalOption(models.Model):
    _name = "garment.approval.option"
    _description = "Approval Card Option"
    _order = "approval_id, sequence, name"

    approval_id = fields.Many2one("garment.approval", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Option", required=True, help="Option code as written on the card, e.g. A.")
    hex = fields.Char(string="Hex", help="Screen colour of the option, e.g. #B9A3DB.")
    note = fields.Char()
