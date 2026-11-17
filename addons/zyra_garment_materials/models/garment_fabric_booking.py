from collections import defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_compare, float_round

BOOKING_OF = [("fabric", "Fabric"), ("trims", "Trims")]
OPEN_PO_STATES = ("draft", "sent", "to approve", "purchase")


class GarmentFabricBooking(models.Model):
    """Materials booked for one production order: what the tech pack needs for the ordered grid,
    what is already in house, what is on open purchase orders and what is still to order."""

    _name = "garment.fabric.booking"
    _description = "Fabric / Trim Booking"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_needed desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Booking", required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency")
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("ordered", "Ordered"),
        ("in_house", "In House"),
    ], default="draft", required=True, tracking=True, copy=False, index=True)

    order_id = fields.Many2one("garment.order", string="Production Order", required=True, index=True,
                               check_company=True, tracking=True,
                               domain="[('state', 'not in', ('closed', 'cancel'))]")
    buyer_id = fields.Many2one(related="order_id.buyer_id", store=True, string="Buyer")
    style_id = fields.Many2one(related="order_id.style_id", store=True, string="Style")
    business_model = fields.Selection(related="order_id.business_model", string="Business Model")
    ex_factory_date = fields.Date(related="order_id.ex_factory_date", string="Ex-factory Date")
    techpack_id = fields.Many2one("zyra.techpack", string="Tech Pack Revision",
                                  compute="_compute_techpack_id", store=True, readonly=False)

    booking_of = fields.Selection(BOOKING_OF, string="Booking Of", required=True, default="fabric")
    booking_date = fields.Date(string="Booking Date", default=fields.Date.context_today, required=True)
    date_needed = fields.Date(string="Needed In House By", tracking=True)
    user_id = fields.Many2one("res.users", string="Booked By", default=lambda self: self.env.user)
    date_in_house = fields.Date(string="In House On", readonly=True, copy=False)
    note = fields.Html(string="Notes")

    line_ids = fields.One2many("garment.fabric.booking.line", "booking_id", string="Materials", copy=True)
    roll_ids = fields.One2many("stock.lot", "fabric_booking_id", string="Rolls")

    # Figures (live: they follow receipts, purchase orders and roll decisions)
    materials_count = fields.Integer(string="Materials Count", compute="_compute_figures")
    materials_in_house_count = fields.Integer(string="Materials In House", compute="_compute_figures")
    materials_short_count = fields.Integer(string="Materials Short", compute="_compute_figures")
    in_house_pct = fields.Float(string="In House %", compute="_compute_figures", digits=(16, 0))
    value_to_order = fields.Monetary(string="Value To Order", compute="_compute_figures")
    qty_required = fields.Float(string="Required", compute="_compute_figures")
    qty_in_house = fields.Float(string="In House", compute="_compute_figures")
    roll_count = fields.Integer(string="Rolls Received Count", compute="_compute_roll_count")
    purchase_count = fields.Integer(string="Purchase Orders", compute="_compute_purchase_count")
    needed_in_days = fields.Integer(string="Needed In (days)", compute="_compute_needed_in")
    needed_in_label = fields.Char(string="Needed In", compute="_compute_needed_in")
    is_short = fields.Boolean(string="Short", compute="_compute_figures", search="_search_is_short",
                              help="Needed-in-house date has passed and not every material is in house.")
    shortage = fields.Selection([("ok", "OK"), ("short", "Short")], string="Shortage",
                                compute="_compute_figures")
    in_house_label = fields.Char(string="In House (materials)", compute="_compute_figures")

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "The booking number must be unique."),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("order_id")
    def _compute_techpack_id(self):
        for booking in self:
            booking.techpack_id = booking.order_id.techpack_id or booking.order_id.style_id.current_techpack_id

    @api.depends("order_id", "order_id.style_id")
    def _compute_display_name(self):
        for booking in self:
            booking.display_name = " · ".join(p for p in (booking.name, booking.order_id.name) if p)

    @api.depends("line_ids", "line_ids.qty_required", "line_ids.qty_in_stock", "line_ids.value_to_order",
                 "date_needed", "state")
    def _compute_figures(self):
        today = fields.Date.context_today(self)
        for booking in self:
            lines = booking.line_ids
            required = sum(lines.mapped("qty_required"))
            covered = sum(min(line.qty_in_stock, line.qty_required) for line in lines)
            in_house = lines.filtered("is_in_house")
            booking.materials_count = len(lines)
            booking.materials_in_house_count = len(in_house)
            booking.materials_short_count = len(lines) - len(in_house)
            booking.qty_required = required
            booking.qty_in_house = covered
            booking.in_house_pct = booking._formula_in_house_pct(covered, required) if lines else 0.0
            booking.value_to_order = sum(lines.mapped("value_to_order"))
            booking.in_house_label = "%s / %s" % (len(in_house), len(lines))
            booking.is_short = bool(
                lines and booking.state != "draft" and booking.date_needed
                and booking.date_needed < today and len(in_house) < len(lines))
            booking.shortage = "short" if booking.is_short else "ok"

    @api.model
    def _formula_in_house_pct(self, covered, required):
        """In house % = Σ min(in house, required) ÷ Σ required × 100 (quantities of the booking's lines)."""
        if not required:
            return 100.0
        return min(100.0, covered / required * 100.0)

    def _search_is_short(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Unsupported search on Short."))
        today = fields.Date.context_today(self)
        candidates = self.search([("state", "in", ("confirmed", "ordered")), ("date_needed", "<", today)])
        short_ids = candidates.filtered("is_short").ids
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", short_ids)]

    def _compute_roll_count(self):
        data = self.env["stock.lot"].sudo()._read_group([("fabric_booking_id", "in", self.ids)], ["fabric_booking_id"],
                                                 ["__count"])
        counts = {booking.id: count for booking, count in data}
        for booking in self:
            booking.roll_count = counts.get(booking.id, 0)

    def _purchase_orders(self):
        return self.sudo().line_ids.purchase_line_ids.order_id

    def _compute_purchase_count(self):
        for booking in self:
            booking.purchase_count = len(booking._purchase_orders())

    @api.depends("date_needed", "state")
    def _compute_needed_in(self):
        today = fields.Date.context_today(self)
        for booking in self:
            if booking.state == "in_house" or not booking.date_needed:
                booking.needed_in_days = 0
                booking.needed_in_label = "—"
            else:
                booking.needed_in_days = (booking.date_needed - today).days
                booking.needed_in_label = _("%s d", booking.needed_in_days)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code(
                    "garment.fabric.booking") or _("New")
            if vals.get("order_id") and not vals.get("company_id"):
                vals["company_id"] = self.env["garment.order"].browse(vals["order_id"]).company_id.id
            if vals.get("order_id") and not vals.get("date_needed"):
                order = self.env["garment.order"].browse(vals["order_id"])
                vals["date_needed"] = order._garment_fabric_needed_date()
        bookings = super().create(vals_list)
        for booking in bookings:
            if not booking.line_ids and booking.techpack_id:
                booking._load_requirements()
        return bookings

    def unlink(self):
        if any(booking.state != "draft" for booking in self):
            raise UserError(_("Only draft bookings can be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Requirements from the tech pack
    # ------------------------------------------------------------------
    def _material_kinds(self):
        self.ensure_one()
        return ("fabric",) if self.booking_of == "fabric" else ("trim", "packing")

    def _requirement_values(self):
        """Lines of the booking from ``zyra.techpack.material_requirements`` and the order grid.

        A material used on every colourway (BoM line without colour) becomes one "All" line; a colourway
        material gets one line per colourway. Required = Σ(pieces × consumption) × (1 + wastage %)."""
        self.ensure_one()
        techpack = self.techpack_id
        order = self.order_id
        if not techpack:
            return []
        qty_by_variant = {(line.colour_id.id, line.size_id.id): line.qty_ordered
                          for line in order.line_ids if line.qty_ordered}
        pieces_by_colour = defaultdict(int)
        for (colour_id, _size_id), qty in qty_by_variant.items():
            pieces_by_colour[colour_id] += qty
        kinds = self._material_kinds()
        bom_lines = techpack.bom_line_ids
        all_colour_products = {
            product for product in bom_lines.product_id
            if not bom_lines.filtered(lambda l, p=product: l.product_id == p and l.colour_id)}
        merged = {}
        for req in techpack.material_requirements(qty_by_variant):
            if req["material_kind"] not in kinds:
                continue
            product = self.env["product.product"].browse(req["product_id"])
            colour_id = False if product in all_colour_products else req["colour_id"]
            key = (req["product_id"], colour_id, req["uom_id"])
            vals = merged.setdefault(key, {
                "product_id": req["product_id"], "colour_id": colour_id, "uom_id": req["uom_id"],
                "material_kind": req["material_kind"], "price_unit": req["price_unit"] or product.standard_price,
                "qty_net": 0.0, "qty_required": 0.0,
                "order_pieces": sum(pieces_by_colour.values()) if not colour_id else pieces_by_colour[colour_id],
            })
            vals["qty_net"] += req["qty_net"]
            vals["qty_required"] += req["qty_with_wastage"]
        result = []
        for sequence, vals in enumerate(merged.values(), start=1):
            net = vals.pop("qty_net")
            pieces = vals["order_pieces"] or 1
            vals["sequence"] = sequence * 10
            vals["consumption"] = net / pieces
            vals["wastage_pct"] = (vals["qty_required"] / net - 1.0) * 100.0 if net else 0.0
            vals["qty_required"] = float_round(vals["qty_required"], precision_digits=2)
            result.append(vals)
        return result

    def _load_requirements(self):
        for booking in self:
            if booking.state != "draft":
                raise UserError(_("Materials can only be reloaded on a draft booking."))
            booking.line_ids = [Command.clear()] + [Command.create(v) for v in booking._requirement_values()]
        return True

    def action_load_requirements(self):
        return self._load_requirements()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_confirm(self):
        for booking in self:
            if booking.state != "draft":
                continue
            if not booking.line_ids:
                raise UserError(_("Booking %s has no materials. Load them from the tech pack first.", booking.name))
            booking.state = "confirmed"
        self._sync_state()
        return True

    def action_draft(self):
        for booking in self:
            if booking._purchase_orders().filtered(lambda po: po.state != "cancel"):
                raise UserError(_("Booking %s has purchase orders; cancel them before resetting to draft.",
                                  booking.name))
        self.write({"state": "draft", "date_in_house": False})
        return True

    def _sync_state(self):
        """Confirmed → Ordered once purchase orders exist; → In House when every material is in house
        (and back when a roll is rejected afterwards). Draft is never changed here."""
        today = fields.Date.context_today(self)
        for booking in self:
            if booking.state == "draft":
                continue
            lines = booking.line_ids
            if lines and all(lines.mapped("is_in_house")):
                if booking.state != "in_house":
                    booking.write({"state": "in_house", "date_in_house": today})
            else:
                has_po = bool(booking._purchase_orders().filtered(lambda po: po.state != "cancel"))
                new_state = "ordered" if has_po else "confirmed"
                if booking.state != new_state:
                    booking.write({"state": new_state, "date_in_house": False})
        return True

    def action_refresh(self):
        self._sync_state()
        return True

    def _check_can_purchase(self):
        user = self.env.user
        allowed = ("zyra_garment_base.group_garment_fabric_store", "zyra_garment_base.group_garment_merchandiser",
                   "purchase.group_purchase_user")
        if not any(user.has_group(g) for g in allowed):
            raise UserError(_("Only the fabric store, merchandisers or purchase users can raise purchase orders."))

    def action_raise_pos(self):
        """One request for quotation per vendor for every material still to order; lines keep the link to
        the booking line so receipts land on the booking (rolls are tagged with it)."""
        self._check_can_purchase()
        purchase_orders = self.env["purchase.order"]
        for booking in self:
            if booking.state == "draft":
                raise UserError(_("Confirm booking %s before raising purchase orders.", booking.name))
            to_order = booking.line_ids.filtered(
                lambda l: float_compare(l.qty_to_order, 0.0, precision_digits=2) > 0)
            if not to_order:
                raise UserError(_("Nothing to order on booking %s: every material is in house or on order.",
                                  booking.name))
            by_vendor = defaultdict(lambda: self.env["garment.fabric.booking.line"])
            missing = []
            for line in to_order:
                vendor = line._vendor()
                if not vendor:
                    missing.append(line.product_id.display_name)
                    continue
                by_vendor[vendor] |= line
            if missing:
                raise UserError(_("Set a vendor on these materials first: %s", ", ".join(missing)))
            planned = datetime.combine(booking.date_needed or fields.Date.context_today(self), time(9, 0))
            for vendor, lines in by_vendor.items():
                po = self.env["purchase.order"].sudo().create({
                    "partner_id": vendor.id,
                    "company_id": booking.company_id.id,
                    "origin": booking.name,
                    "date_planned": planned,
                    "order_line": [Command.create({
                        "product_id": line.product_id.id,
                        "product_qty": float_round(line.qty_to_order, precision_digits=2),
                        "product_uom": line.uom_id.id,
                        "date_planned": planned,
                        "garment_booking_line_id": line.id,
                    }) for line in lines],
                })
                purchase_orders |= po
            booking.message_post(body=_("Purchase orders raised: %s", ", ".join(
                purchase_orders.filtered(lambda po: po.origin == booking.name).mapped("name"))))
        self._sync_state()
        return self._action_view_purchase_orders(purchase_orders)

    def _action_view_purchase_orders(self, orders):
        action = self.env["ir.actions.act_window"]._for_xml_id("purchase.purchase_rfq")
        action["domain"] = [("id", "in", orders.ids)]
        action["context"] = {}
        if len(orders) == 1:
            action.update({"view_mode": "form", "res_id": orders.id,
                           "views": [(self.env.ref("purchase.purchase_order_form").id, "form")]})
        return action

    def action_view_purchase_orders(self):
        self.ensure_one()
        return self._action_view_purchase_orders(self._purchase_orders())

    def action_view_rolls(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_materials.action_garment_roll_board")
        action["domain"] = [("is_fabric_roll", "=", True), ("fabric_booking_id", "=", self.id)]
        action["context"] = {"default_is_fabric_roll": True}
        return action

    def action_print(self):
        return self.env.ref("zyra_garment_materials.action_report_fabric_booking").report_action(self)


class GarmentFabricBookingLine(models.Model):
    _name = "garment.fabric.booking.line"
    _description = "Booking Material Line"
    _order = "booking_id, sequence, id"

    booking_id = fields.Many2one("garment.fabric.booking", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="booking_id.company_id", store=True)
    currency_id = fields.Many2one(related="booking_id.currency_id")
    order_id = fields.Many2one(related="booking_id.order_id", store=True, string="Production Order")
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", string="Material", required=True)
    material_kind = fields.Selection([("fabric", "Fabric"), ("trim", "Trim"), ("packing", "Packing")],
                                     string="Kind", default="fabric", required=True)
    colour_id = fields.Many2one("garment.colour", string="For Colour", help="Empty: every colourway.")
    colour_label = fields.Char(string="Colour", compute="_compute_colour_label")
    order_pieces = fields.Integer(string="Order Pieces")
    consumption = fields.Float(string="Consumption", digits=(16, 4), help="Per piece, in the line unit.")
    wastage_pct = fields.Float(string="Wastage %", digits=(16, 2))
    qty_required = fields.Float(string="Required", digits=(16, 2))
    uom_id = fields.Many2one("uom.uom", string="Unit", required=True)
    price_unit = fields.Float(string="Price", digits="Product Price")

    roll_ids = fields.One2many("stock.lot", "booking_line_id", string="Rolls")
    purchase_line_ids = fields.One2many("purchase.order.line", "garment_booking_line_id", string="PO Lines")

    qty_in_stock = fields.Float(string="In Stock", digits=(16, 2), compute="_compute_quantities",
                                help="Received against this booking: rolls tagged to the line (rejected rolls "
                                     "excluded) or, for untracked materials, purchase receipts.")
    qty_on_hand = fields.Float(string="On Hand", digits=(16, 2), compute="_compute_quantities",
                               help="What is still in the store of the rolls received for this line.")
    qty_used = fields.Float(string="Issued", digits=(16, 2), compute="_compute_quantities")
    qty_open_po = fields.Float(string="On Open POs", digits=(16, 2), compute="_compute_quantities")
    qty_to_order = fields.Float(string="To Order", digits=(16, 2), compute="_compute_quantities")
    value_to_order = fields.Monetary(string="Value To Order", compute="_compute_quantities")
    is_in_house = fields.Boolean(string="In House", compute="_compute_quantities")
    is_short = fields.Boolean(string="Short", compute="_compute_quantities")

    @api.depends("colour_id")
    def _compute_colour_label(self):
        for line in self:
            line.colour_label = line.colour_id.name or _("All")

    def _vendor(self):
        self.ensure_one()
        seller = self.product_id._select_seller(quantity=self.qty_to_order, uom_id=self.uom_id)
        return (seller.partner_id if seller else self.product_id.seller_ids[:1].partner_id)

    @api.depends("qty_required", "price_unit", "uom_id", "product_id", "roll_ids.roll_received_qty",
                 "roll_ids.roll_status", "purchase_line_ids.product_qty", "purchase_line_ids.qty_received",
                 "purchase_line_ids.state")
    def _compute_quantities(self):
        for line in self:
            vals = line._quantity_figures()
            line.update(vals)

    @api.model
    def _formula_to_order(self, required, in_stock, open_po):
        """To order = max(0, required − in stock − on open POs)."""
        return max(0.0, required - in_stock - open_po)

    def _quantity_figures(self):
        self.ensure_one()
        line = self.sudo()
        uom = line.uom_id
        product_uom = line.product_id.uom_id
        in_stock = on_hand = 0.0
        if line.product_id.tracking == "lot" or line.roll_ids:
            for roll in line.roll_ids.filtered(lambda r: r.roll_status != "rejected"):
                in_stock += product_uom._compute_quantity(roll.roll_received_qty, uom, round=False)
                on_hand += product_uom._compute_quantity(max(roll.product_qty, 0.0), uom, round=False)
        else:
            for pol in line.purchase_line_ids.filtered(lambda l: l.state == "purchase"):
                received = pol.product_uom._compute_quantity(pol.qty_received, uom, round=False)
                in_stock += received
            on_hand = in_stock
        open_po = 0.0
        for pol in line.purchase_line_ids.filtered(lambda l: l.state in OPEN_PO_STATES):
            open_po += pol.product_uom._compute_quantity(max(pol.product_qty - pol.qty_received, 0.0), uom,
                                                         round=False)
        to_order = self._formula_to_order(line.qty_required, in_stock, open_po)
        in_house = float_compare(in_stock, line.qty_required, precision_digits=2) >= 0
        return {
            "qty_in_stock": in_stock,
            "qty_on_hand": on_hand,
            "qty_used": max(0.0, in_stock - on_hand),
            "qty_open_po": open_po,
            "qty_to_order": to_order,
            "value_to_order": to_order * line.price_unit,
            "is_in_house": in_house,
            "is_short": not in_house,
        }
