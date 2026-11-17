from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

STAGES = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("ex_factory", "Ex-factory"),
    ("handed_over", "Handed Over"),
    ("on_board", "On Board"),
    ("documents_presented", "Documents Presented"),
    ("paid", "Paid"),
]
SHIPPED_STAGES = ("ex_factory", "handed_over", "on_board", "documents_presented", "paid")
FM_GROUP = "zyra_garment_base.group_garment_factory_manager"


class GarmentShipment(models.Model):
    """One shipment: the cartons of one or more orders of a buyer leaving the factory together."""

    _name = "garment.shipment"
    _description = "Shipment"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "planned_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Shipment", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    stage = fields.Selection(STAGES, default="draft", required=True, tracking=True, index=True, copy=False)
    buyer_id = fields.Many2one("res.partner", string="Buyer", required=True, tracking=True, index=True,
                               domain="[('is_garment_buyer', '=', True)]")
    order_ids = fields.Many2many("garment.order", string="Production Orders", check_company=True,
                                 domain="[('buyer_id', '=', buyer_id), ('state', 'not in', ('draft', 'cancel'))]")
    order_names = fields.Char(string="Orders", compute="_compute_order_names")
    lc_id = fields.Many2one("garment.lc", string="Letter of Credit", tracking=True, check_company=True,
                            domain="[('buyer_id', '=', buyer_id)]")
    final_shipment = fields.Boolean(string="Final Shipment",
                                    help="The last shipment of its orders: pieces short of the order are checked "
                                         "against the tolerance.")
    clerk_id = fields.Many2one("res.users", string="Shipping Clerk", default=lambda self: self.env.user)

    # Transport
    mode = fields.Selection([("sea", "Sea"), ("air", "Air"), ("road", "Road"), ("courier", "Courier")],
                            string="Mode of Transport", default="sea", required=True)
    incoterm_id = fields.Many2one("account.incoterms", string="Incoterm")
    port_loading = fields.Char(string="Port of Loading")
    port_discharge = fields.Char(string="Port of Discharge")
    forwarder = fields.Char(string="Forwarder")
    vessel_flight = fields.Char(string="Vessel / Flight")
    transport_doc_no = fields.Char(string="B/L / AWB No.")

    # Dates
    planned_date = fields.Date(string="Planned Ex-factory", required=True, tracking=True)
    actual_date = fields.Date(string="Actual", tracking=True, copy=False)
    days_late = fields.Integer(string="Days Late", compute="_compute_days_late",
                               help="Actual (or today, while not shipped) minus planned ex-factory, when positive.")
    ex_factory_label = fields.Char(string="Ex-factory", compute="_compute_days_late")

    # Content
    carton_ids = fields.One2many("garment.carton", "shipment_id", string="Carton List")
    carton_count = fields.Integer(string="Cartons", compute="_compute_content", store=True)
    pieces = fields.Integer(string="Pieces", compute="_compute_content", store=True)
    net_weight = fields.Float(string="Net kg", digits=(16, 1), compute="_compute_content", store=True)
    gross_weight = fields.Float(string="Gross kg", digits=(16, 1), compute="_compute_content", store=True)
    volume_cbm = fields.Float(string="Volume (CBM)", digits=(16, 2), compute="_compute_content", store=True)
    value = fields.Monetary(string="Value", compute="_compute_content", store=True)

    # Checks
    hold_count = fields.Integer(string="Holds", compute="_compute_checks",
                                help="Orders whose final inspection has not passed.")
    quality_warning = fields.Text(compute="_compute_checks")
    lc_warning = fields.Text(compute="_compute_checks")
    lc_ok = fields.Boolean(compute="_compute_checks")
    documents_to_prepare = fields.Integer(string="Documents to Prepare", compute="_compute_checks")
    override_reason = fields.Text(string="Override Reason", readonly=True, copy=False)
    override_user_id = fields.Many2one("res.users", string="Overridden By", readonly=True, copy=False)
    override_date = fields.Datetime(string="Overridden On", readonly=True, copy=False)

    # Documents
    picking_ids = fields.One2many("stock.picking", "garment_shipment_id", string="Deliveries")
    delivery_count = fields.Integer(compute="_compute_doc_counts")
    invoice_ids = fields.Many2many("account.move", string="Invoices", copy=False)
    invoice_count = fields.Integer(compute="_compute_doc_counts")

    # ------------------------------------------------------------------ computes
    @api.depends("order_ids.name")
    def _compute_order_names(self):
        for ship in self:
            ship.order_names = ", ".join(ship.order_ids.mapped("name"))

    @api.depends("planned_date", "actual_date", "stage")
    def _compute_days_late(self):
        today = fields.Date.context_today(self)
        for ship in self:
            ref = ship.actual_date or (today if ship.stage not in SHIPPED_STAGES else False)
            late = (ref - ship.planned_date).days if (ref and ship.planned_date) else 0
            ship.days_late = max(late, 0)
            if ship.days_late:
                ship.ex_factory_label = _("%s d late", ship.days_late)
            elif ship.actual_date or ship.stage in SHIPPED_STAGES:
                ship.ex_factory_label = _("On time")
            elif ship.planned_date:
                ship.ex_factory_label = _("in %s d", (ship.planned_date - today).days)
            else:
                ship.ex_factory_label = False

    @api.depends("carton_ids.pieces", "carton_ids.net_weight", "carton_ids.gross_weight", "carton_ids.cbm",
                 "carton_ids.line_ids.qty", "carton_ids.order_id.price_unit")
    def _compute_content(self):
        for ship in self:
            cartons = ship.carton_ids
            ship.carton_count = len(cartons)
            ship.pieces = sum(cartons.mapped("pieces"))
            ship.net_weight = sum(cartons.mapped("net_weight"))
            ship.gross_weight = sum(cartons.mapped("gross_weight"))
            ship.volume_cbm = sum(cartons.mapped("cbm"))
            ship.value = sum(c.pieces * c.order_id.price_unit for c in cartons)

    def _compute_doc_counts(self):
        for ship in self:
            ship.delivery_count = len(ship.picking_ids)
            ship.invoice_count = len(ship.invoice_ids)

    def _ship_date(self):
        self.ensure_one()
        return self.actual_date or fields.Date.context_today(self)

    def _final_inspection_holds(self):
        """Orders of the shipment whose final inspection has not passed (quality, soft dependency)."""
        self.ensure_one()
        return self.order_ids.filtered(lambda o: not o._garment_shipping_final_ok())

    def _short_shipment_warning(self):
        self.ensure_one()
        if not self.final_shipment or not self.order_ids:
            return False
        ordered = sum(self.order_ids.mapped("qty_ordered"))
        shipped_before = sum(self.order_ids.mapped("qty_shipped"))
        shipped = shipped_before if self.stage in SHIPPED_STAGES else shipped_before + self.pieces
        tolerance = self.lc_id.tolerance_pct if self.lc_id else 0.0
        if ordered and shipped < ordered * (1 - tolerance / 100.0):
            return _("The final shipment closes at %(shipped)s pieces against %(ordered)s ordered, below the "
                     "%(tol)s%% tolerance.", shipped=shipped, ordered=ordered, tol="%g" % tolerance)
        return False

    def _shipping_warnings(self):
        """Every reason this shipment needs a Factory Manager override before it leaves."""
        self.ensure_one()
        warnings = []
        for order in self._final_inspection_holds():
            warnings.append(_("Final inspection of %s has not passed.", order.name))
        if self.lc_id:
            warnings += self.lc_id._shipment_warnings(self._ship_date(), self.value)
        short = self._short_shipment_warning()
        if short:
            warnings.append(short)
        return warnings

    @api.depends("order_ids", "lc_id", "actual_date", "value", "stage", "final_shipment", "pieces")
    def _compute_checks(self):
        for ship in self:
            holds = ship._final_inspection_holds()
            ship.hold_count = len(holds)
            ship.quality_warning = "\n".join(
                _("Final inspection of %s has not passed: the shipment is blocked until a re-inspection "
                  "passes or a Factory Manager overrides.", o.name) for o in holds) or False
            lc_lines = ship.lc_id._shipment_warnings(ship._ship_date(), ship.value) if ship.lc_id else []
            short = ship._short_shipment_warning()
            if short:
                lc_lines.append(short)
            ship.lc_warning = "\n".join(lc_lines) or False
            ship.lc_ok = not lc_lines
            docs = [d for d in (ship.lc_id.documents or "").replace(" and ", ",").split(",") if d.strip()]
            ship.documents_to_prepare = 0 if ship.stage in ("documents_presented", "paid") else len(docs)

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.shipment") or _("New")
        return super().create(vals_list)

    def unlink(self):
        if self.filtered(lambda s: s.stage != "draft"):
            raise UserError(_("Only draft shipments can be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------ cartons
    def action_add_packed_cartons(self):
        """Put every packed carton of the shipment's orders that is not on a shipment yet on this one."""
        for ship in self:
            if ship.stage not in ("draft", "confirmed"):
                raise UserError(_("Cartons are added before the shipment leaves the factory."))
            cartons = self.env["garment.carton"].search([
                ("order_id", "in", ship.order_ids.ids), ("state", "=", "packed"), ("shipment_id", "=", False)])
            cartons.write({"shipment_id": ship.id})
        return True

    def action_remove_cartons(self):
        for ship in self:
            if ship.stage not in ("draft", "confirmed"):
                raise UserError(_("Cartons cannot leave a shipment that has left the factory."))
            ship.carton_ids.write({"shipment_id": False})
        return True

    # ------------------------------------------------------------------ stages
    def action_confirm(self):
        for ship in self:
            if ship.stage != "draft":
                raise UserError(_("Only a draft shipment can be confirmed."))
            if not ship.carton_ids:
                raise UserError(_("Add the packed cartons before confirming the shipment."))
        self.stage = "confirmed"

    def action_ex_factory(self):
        """Goods leave the factory: needs every check clear or a Factory Manager override; ships the cartons
        through a stock delivery and posts 'shipped' to the orders."""
        for ship in self:
            if ship.stage != "confirmed":
                raise UserError(_("Confirm the shipment before it leaves the factory."))
            if ship.carton_ids.filtered(lambda c: c.state != "packed"):
                raise UserError(_("Every carton on the shipment must be packed."))
            warnings = ship._shipping_warnings()
            if warnings and not ship.override_user_id:
                raise UserError(_("This shipment cannot leave the factory yet:\n%s\n\nA Factory Manager can "
                                  "override with a reason.", "\n".join("• " + w for w in warnings)))
            if not ship.actual_date:
                ship.actual_date = fields.Date.context_today(ship)
            ship._create_delivery()
            ship._post_shipped()
            ship.carton_ids.write({"state": "shipped"})
            ship.stage = "ex_factory"
        return True

    def action_handed_over(self):
        self._advance("ex_factory", "handed_over")

    def action_on_board(self):
        self._advance("handed_over", "on_board")

    def action_documents_presented(self):
        """Documents go to the bank: one drawing on the credit for the shipment value."""
        for ship in self:
            ship._advance("on_board", "documents_presented")
            if ship.lc_id and ship.value:
                warnings = ship.lc_id._shipment_warnings(ship.actual_date, 0.0)
                self.env["garment.lc.drawing"].create({
                    "lc_id": ship.lc_id.id, "shipment_id": ship.id, "amount": ship.value,
                    "date": fields.Date.context_today(ship), "note": _("Documents presented"),
                })
                if warnings:
                    ship.message_post(body=_("Presented under %(lc)s with warnings: %(w)s", lc=ship.lc_id.name,
                                             w=" ".join(w[0].lower() + w[1:] for w in warnings)))
                else:
                    ship.message_post(body=_("Presented under %s.", ship.lc_id.name))
        return True

    def action_paid(self):
        self._advance("documents_presented", "paid")

    def _advance(self, from_stage, to_stage):
        for ship in self:
            if ship.stage != from_stage:
                raise UserError(_("The shipment must be at %(a)s to move to %(b)s.",
                                  a=dict(STAGES)[from_stage], b=dict(STAGES)[to_stage]))
            ship.stage = to_stage
        return True

    def action_draft(self):
        for ship in self:
            if ship.stage != "confirmed":
                raise UserError(_("Only a confirmed shipment goes back to draft."))
        self.stage = "draft"

    # ------------------------------------------------------------------ override
    def action_open_override(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Manager Override"),
            "res_model": "garment.shipment.override.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_shipment_id": self.id},
        }

    def _garment_override(self, reason):
        """Record a Factory Manager override with its reason (logged in the chatter)."""
        self.ensure_one()
        if not self.env.user.has_group(FM_GROUP):
            raise AccessError(_("Only a Factory Manager can override the shipping checks."))
        reason = (reason or "").strip()
        if not reason:
            raise UserError(_("Give the reason for the override."))
        warnings = self._shipping_warnings()
        self.sudo().write({"override_reason": reason, "override_user_id": self.env.user.id,
                           "override_date": fields.Datetime.now()})
        body = _("Manager override: %s", reason)
        if warnings:
            body += "\n" + _("Overridden checks: %s", " ".join(warnings))
        self.message_post(body=body, author_id=self.env.user.partner_id.id)
        return True

    # ------------------------------------------------------------------ stock and progress
    def _cell_quantities(self):
        """{(order, colour, size): qty} of the cartons on the shipment."""
        totals = defaultdict(int)
        for carton in self.carton_ids:
            for line in carton.line_ids:
                totals[(carton.order_id, line.colour_id, line.size_id, carton.plan_id)] += line.qty
        return totals

    def _create_delivery(self):
        """One outgoing stock picking per shipment, one move per garment variant, validated."""
        self.ensure_one()
        qty_by_variant = defaultdict(int)
        for (order, colour, size, plan), qty in self._cell_quantities().items():
            variant = plan._garment_variant(colour, size)
            if variant and qty:
                qty_by_variant[variant] += qty
        if not qty_by_variant:
            self.message_post(body=_("No garment variants on this shipment: no stock delivery was made."))
            return self.env["stock.picking"]
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)], limit=1)
        picking_type = warehouse.out_type_id
        if not picking_type:
            raise UserError(_("The company has no delivery operation type."))
        src = picking_type.default_location_src_id
        dest = self.buyer_id.property_stock_customer or self.env.ref("stock.stock_location_customers")
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "partner_id": self.buyer_id.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "origin": self.name,
            "garment_shipment_id": self.id,
            "company_id": self.company_id.id,
            "move_ids": [fields.Command.create({
                "name": variant.display_name,
                "product_id": variant.id,
                "product_uom_qty": qty,
                "product_uom": variant.uom_id.id,
                "location_id": src.id,
                "location_dest_id": dest.id,
                "company_id": self.company_id.id,
            }) for variant, qty in qty_by_variant.items()],
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        return picking

    def _post_shipped(self):
        self.ensure_one()
        for (order, colour, size, _plan), qty in self._cell_quantities().items():
            if qty:
                order._garment_add_progress("shipped", colour.id, size.id, qty, ref=self.name)

    # ------------------------------------------------------------------ documents
    def action_create_invoice(self):
        """Draft customer invoice of the shipment: one line per order (pieces × order price)."""
        self.ensure_one()
        if self.invoice_ids.filtered(lambda m: m.state != "cancel"):
            raise UserError(_("This shipment is already invoiced."))
        pieces = defaultdict(int)
        for carton in self.carton_ids:
            pieces[carton.order_id] += carton.pieces
        if not pieces:
            raise UserError(_("The shipment has no cartons to invoice."))
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.buyer_id.id,
            "invoice_origin": self.name,
            "invoice_incoterm_id": self.incoterm_id.id,
            "company_id": self.company_id.id,
            "invoice_line_ids": [fields.Command.create({
                "name": "%s · %s" % (order.display_name, order.style_id.name),
                "quantity": qty,
                "price_unit": order.price_unit,
            }) for order, qty in pieces.items()],
        })
        self.invoice_ids = [fields.Command.link(move.id)]
        return self.action_view_invoices()

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoices"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.invoice_ids.ids)],
            "context": {"default_move_type": "out_invoice"},
        }

    def action_view_deliveries(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Deliveries"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", self.picking_ids.ids)],
        }

    def action_view_cartons(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_shipping.action_garment_carton")
        action["domain"] = [("shipment_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_print_packing_list(self):
        return self.env.ref("zyra_garment_shipping.action_report_packing_list").report_action(self)

    # ------------------------------------------------------------------ packing list
    def _packing_list_data(self):
        """Rows for the printed packing list: consecutive cartons with the same content share a row."""
        self.ensure_one()
        return self.env["garment.carton"]._packing_list_rows(self.carton_ids)
