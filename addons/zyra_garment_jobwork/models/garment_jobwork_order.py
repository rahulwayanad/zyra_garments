from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class GarmentJobworkOrder(models.Model):
    _name = "garment.jobwork.order"
    _description = "Job Work Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Job Work No.", required=True, copy=False, readonly=True, default="/")
    title = fields.Char(compute="_compute_title", string="Title")
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    state = fields.Selection([
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("partly_received", "Partly Received"),
        ("received", "Received"),
        ("billed", "Billed"),
        ("cancel", "Cancelled"),
    ], default="draft", required=True, tracking=True, group_expand="_group_expand_states", copy=False)
    process = fields.Selection([
        ("sewing", "Sewing"),
        ("wash", "Washing"),
        ("print", "Printing"),
        ("embroidery", "Embroidery"),
    ], required=True, default="sewing", tracking=True)
    production_order_id = fields.Many2one("garment.order", string="Production Order", index=True)
    style_id = fields.Many2one(related="production_order_id.style_id", store=True)
    buyer_id = fields.Many2one(related="production_order_id.buyer_id", store=True)
    user_id = fields.Many2one("res.users", string="Responsible", default=lambda s: s.env.user, tracking=True)
    in_house = fields.Boolean(string="Done In-house")
    vendor_id = fields.Many2one("res.partner", string="Subcontractor", tracking=True,
                                domain="[('is_jobwork_vendor', '=', True)]")
    rate = fields.Monetary(string="Rate", help="Agreed rate per piece", tracking=True)
    allowance_pct = fields.Float(string="Loss Allowance %", default=2.0,
                                 help="Process loss the vendor is allowed before it is flagged")
    bundle_ids = fields.Many2many("garment.bundle", string="Bundles")
    qty_sent = fields.Integer(string="Sent", compute="_compute_qty_sent", store=True, readonly=False,
                              tracking=True)
    date_issue = fields.Date(string="Issue Date", default=fields.Date.context_today)
    date_expected = fields.Date(string="Expected Back")
    date_received = fields.Date(string="Fully Received On", readonly=True, copy=False)
    turnaround_days = fields.Integer(string="Turnaround (days)", compute="_compute_turnaround")
    receipt_ids = fields.One2many("garment.jobwork.receipt", "order_id", string="Returns")
    qty_good = fields.Integer(string="Good Back", compute="_compute_qty", store=True)
    qty_rejected = fields.Integer(string="Rejected Back", compute="_compute_qty", store=True)
    qty_short = fields.Integer(string="Short", readonly=True, copy=False, tracking=True)
    qty_rejected_short = fields.Integer(string="Rejected or Short", compute="_compute_qty", store=True)
    qty_pending = fields.Integer(string="Pending", compute="_compute_qty", store=True)
    process_loss_pct = fields.Float(string="Process Loss %", compute="_compute_qty", store=True,
                                    digits=(16, 1))
    loss_over_allowance = fields.Boolean(compute="_compute_qty", store=True)
    qty_billable = fields.Float(string="Billable Quantity", compute="_compute_qty", store=True, digits=(16, 2))
    jobwork_value = fields.Monetary(string="Job Work Value", compute="_compute_value", store=True)
    bill_due = fields.Monetary(string="Bill Due", compute="_compute_value", store=True)
    is_overdue = fields.Boolean(string="Overdue", compute="_compute_is_overdue", search="_search_is_overdue")
    purchase_ids = fields.One2many("purchase.order", "garment_jobwork_id", string="Purchase Orders")
    purchase_count = fields.Integer(compute="_compute_purchase_count")
    move_ids = fields.One2many("stock.move", "garment_jobwork_id", string="Stock Moves")
    note = fields.Text()

    @api.model
    def _group_expand_states(self, states, domain):
        return ["sent", "partly_received", "received", "billed"]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.jobwork.order") or "/"
        return super().create(vals_list)

    @api.depends("process")
    def _compute_title(self):
        labels = dict(self._fields["process"]._description_selection(self.env))
        for rec in self:
            rec.title = _("Outsourced %s", (labels.get(rec.process) or "").lower())

    @api.depends("process", "production_order_id")
    def _compute_display_name(self):
        labels = dict(self._fields["process"]._description_selection(self.env))
        for rec in self:
            parts = [labels.get(rec.process), rec.production_order_id.name]
            rec.display_name = " · ".join(p for p in parts if p) or rec.name

    @api.depends("bundle_ids.pieces")
    def _compute_qty_sent(self):
        for rec in self:
            if rec.bundle_ids:
                rec.qty_sent = sum(rec.bundle_ids.mapped("pieces"))
            else:
                rec.qty_sent = rec.qty_sent or 0

    @api.depends("qty_sent", "qty_short", "allowance_pct", "receipt_ids.qty_good", "receipt_ids.qty_rejected")
    def _compute_qty(self):
        for rec in self:
            good = sum(rec.receipt_ids.mapped("qty_good"))
            rej = sum(rec.receipt_ids.mapped("qty_rejected"))
            rec.qty_good = good
            rec.qty_rejected = rej
            rec.qty_rejected_short = rej + rec.qty_short
            rec.qty_pending = max(rec.qty_sent - good - rej - rec.qty_short, 0)
            lost = rej + rec.qty_short
            rec.process_loss_pct = (lost / rec.qty_sent * 100.0) if rec.qty_sent else 0.0
            rec.loss_over_allowance = rec.process_loss_pct > rec.allowance_pct
            rec.qty_billable = good

    @api.depends("qty_billable", "rate", "state")
    def _compute_value(self):
        for rec in self:
            rec.jobwork_value = rec.qty_billable * rec.rate
            rec.bill_due = 0.0 if rec.state == "billed" or rec.in_house else rec.jobwork_value

    @api.depends("date_issue", "date_received")
    def _compute_turnaround(self):
        for rec in self:
            if rec.date_issue and rec.date_received:
                rec.turnaround_days = (rec.date_received - rec.date_issue).days
            else:
                rec.turnaround_days = 0

    @api.depends("state", "date_expected")
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(rec.state in ("sent", "partly_received") and rec.date_expected
                                  and rec.date_expected < today)

    def _search_is_overdue(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Unsupported search on Overdue."))
        today = fields.Date.context_today(self)
        domain = [("state", "in", ("sent", "partly_received")), ("date_expected", "<", today)]
        if (operator == "=") == value:
            return domain
        return ["!", "&"] + domain

    def _compute_purchase_count(self):
        for rec in self:
            rec.purchase_count = len(rec.purchase_ids)

    @api.constrains("allowance_pct", "rate", "qty_sent")
    def _check_values(self):
        for rec in self:
            if rec.allowance_pct < 0 or rec.allowance_pct > 100:
                raise ValidationError(_("Loss allowance must be between 0 and 100 %."))
            if rec.rate < 0 or rec.qty_sent < 0:
                raise ValidationError(_("Rate and quantity sent cannot be negative."))

    # ---- stock -------------------------------------------------------------------------------------
    def _jobwork_locations(self):
        self.ensure_one()
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("No warehouse for company %s.", self.company_id.name))
        vendor_loc = self.env.ref("zyra_garment_jobwork.stock_location_jobwork")
        return warehouse.lot_stock_id, vendor_loc

    def _jobwork_move(self, qty, src, dest, label):
        self.ensure_one()
        if qty <= 0:
            return self.env["stock.move"]
        product = self.env.ref("zyra_garment_jobwork.product_jobwork_pieces")
        move = self.env["stock.move"].sudo().create({
            "name": "%s: %s" % (self.name, label),
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": qty,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "company_id": self.company_id.id,
            "origin": self.name,
            "garment_jobwork_id": self.id,
        })
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    # ---- actions -----------------------------------------------------------------------------------
    def action_send(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("%s is already sent.", rec.name))
            if rec.qty_sent <= 0:
                raise UserError(_("Enter the pieces or bundles sent before sending %s.", rec.name))
            if not rec.in_house and not rec.vendor_id:
                raise UserError(_("Choose the subcontractor of %s.", rec.name))
            stock, vendor = rec._jobwork_locations()
            if not rec.in_house:
                rec._jobwork_move(rec.qty_sent, stock, vendor, _("sent"))
            rec.write({"state": "sent", "date_issue": rec.date_issue or fields.Date.context_today(rec)})
        return True

    def _garment_receive(self, qty_good, qty_rejected=0, date=None):
        """Record one return from the vendor. Returns the receipt."""
        self.ensure_one()
        if self.state not in ("sent", "partly_received"):
            raise UserError(_("%s is not waiting for pieces.", self.name))
        if qty_good < 0 or qty_rejected < 0 or not (qty_good + qty_rejected):
            raise UserError(_("Enter the good and rejected pieces received."))
        if qty_good + qty_rejected > self.qty_pending:
            raise ValidationError(_("Only %(p)s pieces are pending on %(n)s.", p=self.qty_pending, n=self.name))
        receipt = self.env["garment.jobwork.receipt"].create({
            "order_id": self.id,
            "date": date or fields.Date.context_today(self),
            "qty_good": qty_good,
            "qty_rejected": qty_rejected,
        })
        if not self.in_house:
            stock, vendor = self._jobwork_locations()
            self._jobwork_move(qty_good + qty_rejected, vendor, stock, _("received back"))
        self._update_receipt_state(receipt.date)
        return receipt

    def _demo_receive(self, qty_good, qty_rejected=0):
        for rec in self:
            rec._garment_receive(qty_good, qty_rejected)
        return True

    def _update_receipt_state(self, date=None):
        for rec in self:
            if rec.qty_pending == 0:
                rec.write({"state": "received", "date_received": date or fields.Date.context_today(rec)})
            else:
                rec.state = "partly_received"

    def action_close_short(self):
        """Close the order: pieces still pending at the vendor are written off as short."""
        for rec in self:
            if rec.state not in ("sent", "partly_received"):
                raise UserError(_("%s is not waiting for pieces.", rec.name))
            short = rec.qty_pending
            if short and not rec.in_house:
                stock, vendor = rec._jobwork_locations()
                scrap = self.env["stock.location"].search(
                    [("scrap_location", "=", True), ("company_id", "in", (rec.company_id.id, False))], limit=1)
                if scrap:
                    rec._jobwork_move(short, vendor, scrap, _("short"))
            rec.qty_short += short
            rec.message_post(body=_("Closed short: %s pieces written off.", short))
            rec._update_receipt_state()
        return True

    def action_bill(self):
        """Raise the purchase order at the agreed rate for the accepted (good) pieces only."""
        service = self.env.ref("zyra_garment_jobwork.product_jobwork_service")
        for rec in self:
            if rec.state != "received":
                raise UserError(_("%s can be billed only once all pieces are back or closed short.", rec.name))
            if rec.in_house:
                rec.state = "billed"
                continue
            po = self.env["purchase.order"].sudo().create({
                "partner_id": rec.vendor_id.id,
                "company_id": rec.company_id.id,
                "origin": rec.name,
                "garment_jobwork_id": rec.id,
                "order_line": [Command.create({
                    "product_id": service.id,
                    "name": "%s · %s" % (rec.name, rec.display_name),
                    "product_qty": rec.qty_billable,
                    "product_uom": service.uom_po_id.id,
                    "price_unit": rec.rate,
                    "taxes_id": [Command.clear()],
                })],
            })
            po.button_confirm()
            rec.state = "billed"
            rec.message_post(body=_("Purchase order %(po)s raised for a billable quantity of %(q)s.",
                                    po=po.name, q=int(rec.qty_billable)))
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only a draft job work order can be cancelled."))
            rec.state = "cancel"
        return True

    def action_view_purchases(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("purchase.purchase_form_action")
        action["domain"] = [("id", "in", self.purchase_ids.ids)]
        if len(self.purchase_ids) == 1:
            action.update(res_id=self.purchase_ids.id, views=[(False, "form")])
        return action

    def action_print_challan(self):
        return self.env.ref("zyra_garment_jobwork.action_report_delivery_challan").report_action(self)


class GarmentJobworkReceipt(models.Model):
    _name = "garment.jobwork.receipt"
    _description = "Job Work Return"
    _order = "date, id"

    order_id = fields.Many2one("garment.jobwork.order", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    qty_good = fields.Integer(string="Good")
    qty_rejected = fields.Integer(string="Rejected")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    garment_jobwork_id = fields.Many2one("garment.jobwork.order", string="Job Work Order", index=True,
                                         copy=False)


class StockMove(models.Model):
    _inherit = "stock.move"

    garment_jobwork_id = fields.Many2one("garment.jobwork.order", string="Job Work Order", index=True,
                                         copy=False)


class GarmentJobworkReceiptWizard(models.TransientModel):
    _name = "garment.jobwork.receipt.wizard"
    _description = "Receive Job Work Pieces"

    order_id = fields.Many2one("garment.jobwork.order", required=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    qty_good = fields.Integer(string="Good")
    qty_rejected = fields.Integer(string="Rejected")

    def action_confirm_receipt(self):
        self.ensure_one()
        self.order_id._garment_receive(self.qty_good, self.qty_rejected, date=self.date)
        return {"type": "ir.actions.act_window_close"}
