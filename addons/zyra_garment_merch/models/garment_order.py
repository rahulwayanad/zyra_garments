from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

PROGRESS_STAGES = ("cut", "sewn", "packed", "shipped")
OPEN_STATES = ("draft", "confirmed", "in_production", "packed")


class GarmentOrder(models.Model):
    """Production order (one per style and buyer order) holding the size × colour grid."""

    _name = "garment.order"
    _description = "Garment Production Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "ex_factory_date, id desc"
    _check_company_auto = True

    name = fields.Char(string="Order No.", required=True, copy=False, readonly=True, index=True,
                       default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, index=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency")
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("in_production", "In Production"),
        ("packed", "Packed"),
        ("shipped", "Shipped"),
        ("closed", "Completed"),
        ("cancel", "Cancelled"),
    ], default="draft", required=True, tracking=True, copy=False, index=True)

    # Buyer
    sale_order_id = fields.Many2one("sale.order", string="Sale Order", copy=False, index=True,
                                    check_company=True)
    sale_order_name = fields.Char(related="sale_order_id.name", string="Sale Order No.")
    buyer_id = fields.Many2one("res.partner", string="Buyer", required=True, tracking=True, index=True,
                               domain="[('is_garment_buyer', '=', True)]")
    buyer_po = fields.Char(string="Buyer PO No.", tracking=True)
    business_model = fields.Selection([
        ("fob", "FOB / full package"),
        ("cmt", "CMT / cut-make-trim"),
    ], default="fob", required=True)
    merchandiser_id = fields.Many2one("res.users", string="Merchandiser", tracking=True,
                                      default=lambda self: self.env.user)

    # Style
    style_id = fields.Many2one("garment.style", string="Style", required=True, tracking=True, index=True,
                               check_company=True)
    techpack_id = fields.Many2one("zyra.techpack", string="Tech Pack Revision", tracking=True,
                                  domain="[('style_id', '=', style_id)]")
    image_128 = fields.Image(related="style_id.image_128", string="Sketch")
    colour_ids = fields.Many2many("garment.colour", string="Colourways")
    size_range_id = fields.Many2one(related="style_id.size_range_id")
    size_ids = fields.Many2many("garment.size", string="Sizes",
                                domain="[('range_id', '=', size_range_id)]")

    # Delivery
    date_order = fields.Date(string="Order Date", default=fields.Date.context_today, required=True)
    ex_factory_date = fields.Date(string="Ex-factory Date", required=True, tracking=True)
    days_to_ex_factory = fields.Integer(string="Days to Ex-factory", compute="_compute_lateness",
                                        help="Days left until the ex-factory date (negative = past it).")
    is_late = fields.Boolean(string="Late", compute="_compute_lateness", search="_search_is_late",
                             help="Past the ex-factory date and not fully shipped.")
    sewing_line_id = fields.Many2one("mrp.workcenter", string="Sewing Line", tracking=True,
                                     check_company=True)

    # Grid
    line_ids = fields.One2many("garment.order.line", "order_id", string="Size and Colour Grid", copy=True)
    progress_ids = fields.One2many("garment.order.progress", "order_id", string="Postings")
    is_amending = fields.Boolean(string="Amending", copy=False,
                                 help="Set by Amend Order: the grid can be changed on a confirmed order.")
    qty_ordered = fields.Integer(string="Order Qty", compute="_compute_totals", store=True)
    qty_cut = fields.Integer(string="Cut", compute="_compute_totals", store=True)
    qty_sewn = fields.Integer(string="Sewn", compute="_compute_totals", store=True)
    qty_packed = fields.Integer(string="Packed", compute="_compute_totals", store=True)
    qty_shipped = fields.Integer(string="Shipped", compute="_compute_totals", store=True)
    qty_balance = fields.Integer(string="Balance", compute="_compute_totals", store=True,
                                 help="Ordered minus shipped.")
    packed_pct = fields.Float(string="Packed %", compute="_compute_totals", store=True, aggregator="avg")

    # Money
    price_unit = fields.Monetary(string="Price / pc", tracking=True)
    order_value = fields.Monetary(string="Order Value", compute="_compute_totals", store=True)

    # Planned cost (read from zyra_garment_costing when installed)
    planned_material_pc = fields.Monetary(string="Planned Material / pc", compute="_compute_planned_cost")
    planned_making_pc = fields.Monetary(string="Planned Making Cost / pc", compute="_compute_planned_cost")
    planned_other_pc = fields.Monetary(string="Planned Other Cost / pc", compute="_compute_planned_cost")
    planned_margin_pct = fields.Float(string="Planned Margin %", compute="_compute_planned_cost")
    cost_sheet_ref = fields.Reference(selection="_selection_cost_sheet", string="Approved Cost Sheet",
                                      compute="_compute_planned_cost")
    has_cost_sheet = fields.Boolean(compute="_compute_planned_cost")
    planned_margin_low = fields.Boolean(compute="_compute_planned_cost",
                                        help="Planned margin under the company margin floor.")

    # Samples and T&A
    sample_ids = fields.One2many("garment.sample", "order_id", string="Samples")
    sample_count = fields.Integer(compute="_compute_counts")
    pp_sample_status = fields.Char(string="PP Sample", compute="_compute_counts")
    pp_sample_ok = fields.Boolean(compute="_compute_counts")
    tna_template_id = fields.Many2one("garment.tna.template", string="T&A Template")
    milestone_ids = fields.One2many("garment.tna.milestone", "order_id", string="Milestones", copy=False)
    milestone_count = fields.Integer(compute="_compute_counts")
    milestone_done_count = fields.Integer(compute="_compute_counts")
    milestone_overdue_count = fields.Integer(compute="_compute_counts")
    posting_count = fields.Integer(compute="_compute_counts")
    note = fields.Html(string="Notes")

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "The production order number must be unique."),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("name", "style_id.code")
    def _compute_display_name(self):
        for order in self:
            order.display_name = " · ".join(p for p in (order.name, order.style_id.code) if p)

    @api.depends("line_ids.qty_ordered", "line_ids.qty_cut", "line_ids.qty_sewn",
                 "line_ids.qty_packed", "line_ids.qty_shipped", "price_unit")
    def _compute_totals(self):
        for order in self:
            lines = order.line_ids
            order.qty_ordered = sum(lines.mapped("qty_ordered"))
            order.qty_cut = sum(lines.mapped("qty_cut"))
            order.qty_sewn = sum(lines.mapped("qty_sewn"))
            order.qty_packed = sum(lines.mapped("qty_packed"))
            order.qty_shipped = sum(lines.mapped("qty_shipped"))
            order.qty_balance = order.qty_ordered - order.qty_shipped
            order.packed_pct = (order.qty_packed * 100.0 / order.qty_ordered) if order.qty_ordered else 0.0
            order.order_value = order.price_unit * order.qty_ordered

    @api.depends("ex_factory_date", "state", "qty_shipped", "qty_ordered")
    def _compute_lateness(self):
        today = fields.Date.context_today(self)
        for order in self:
            if order.ex_factory_date:
                order.days_to_ex_factory = (order.ex_factory_date - today).days
                order.is_late = order._is_late_on(today)
            else:
                order.days_to_ex_factory = 0
                order.is_late = False

    def _is_late_on(self, day):
        """Rule: an order is late when the ex-factory date has passed and it is not fully shipped."""
        self.ensure_one()
        return bool(
            self.ex_factory_date
            and self.ex_factory_date < day
            and self.state in OPEN_STATES
            and self.qty_shipped < self.qty_ordered
        )

    def _search_is_late(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("Unsupported search on Late."))
        today = fields.Date.context_today(self)
        late_ids = self.search([
            ("ex_factory_date", "<", today),
            ("state", "in", list(OPEN_STATES)),
        ]).filtered(lambda o: o._is_late_on(today)).ids
        positive = (operator == "=") == bool(value)
        return [("id", "in" if positive else "not in", late_ids)]

    @api.depends("sample_ids.state", "sample_ids.sample_type", "milestone_ids.actual_date",
                 "milestone_ids.planned_date", "progress_ids")
    def _compute_counts(self):
        today = fields.Date.context_today(self)
        state_labels = dict(self.env["garment.sample"]._fields["state"]._description_selection(self.env))
        for order in self:
            order.sample_count = len(order.sample_ids)
            pp = order.sample_ids.filtered(lambda s: s.sample_type == "pp").sorted("id")
            if pp:
                last = pp[-1]
                order.pp_sample_status = state_labels.get(last.state)
                order.pp_sample_ok = last.state == "approved"
            else:
                order.pp_sample_status = _("Not requested")
                order.pp_sample_ok = False
            order.milestone_count = len(order.milestone_ids)
            order.milestone_done_count = len(order.milestone_ids.filtered("actual_date"))
            order.milestone_overdue_count = len(order.milestone_ids.filtered(
                lambda m: not m.actual_date and m.planned_date and m.planned_date < today))
            order.posting_count = len(order.progress_ids)

    @api.model
    def _selection_cost_sheet(self):
        if "garment.cost.sheet" in self.env:
            return [("garment.cost.sheet", self.env._("Cost Sheet"))]
        return []

    def _get_approved_cost_sheet(self):
        """Soft link to zyra_garment_costing: the approved cost sheet of the order's tech pack (or style)."""
        self.ensure_one()
        if "garment.cost.sheet" not in self.env:
            return None
        Sheet = self.env["garment.cost.sheet"]
        domain = [("state", "=", "approved")]
        if self.techpack_id and "techpack_id" in Sheet._fields:
            domain.append(("techpack_id", "=", self.techpack_id.id))
        elif "style_id" in Sheet._fields and self.style_id:
            domain.append(("style_id", "=", self.style_id.id))
        elif self.techpack_id or self.style_id:
            return Sheet
        return Sheet.search(domain, order="id desc", limit=1)

    @api.depends("techpack_id", "style_id")
    def _compute_planned_cost(self):
        def first(rec, names):
            for name in names:
                if name in rec._fields:
                    return rec[name] or 0.0
            return 0.0

        for order in self:
            sheet = order._get_approved_cost_sheet() if order.id or order.style_id else None
            if sheet:
                order.has_cost_sheet = True
                order.cost_sheet_ref = "%s,%s" % (sheet._name, sheet.id)
                order.planned_material_pc = first(sheet, ("material_cost", "material_cost_pc",
                                                          "material_per_piece"))
                order.planned_making_pc = first(sheet, ("making_cost", "making_cost_pc", "making_per_piece"))
                order.planned_other_pc = first(sheet, ("other_cost", "other_cost_pc", "overhead_cost",
                                                       "process_cost"))
                order.planned_margin_pct = first(sheet, ("margin_pct", "margin_percent"))
                order.planned_margin_low = order.planned_margin_pct < order.company_id.margin_floor_pct
            else:
                order.has_cost_sheet = False
                order.cost_sheet_ref = False
                order.planned_material_pc = order.planned_making_pc = order.planned_other_pc = 0.0
                order.planned_margin_pct = 0.0
                order.planned_margin_low = False

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains("techpack_id", "style_id")
    def _check_techpack_style(self):
        for order in self:
            if order.techpack_id and order.techpack_id.style_id != order.style_id:
                raise ValidationError(_("The tech pack revision must belong to the order's style."))

    @api.constrains("date_order", "ex_factory_date")
    def _check_dates(self):
        for order in self:
            if order.date_order and order.ex_factory_date and order.ex_factory_date < order.date_order:
                raise ValidationError(_("The ex-factory date cannot be before the order date."))

    # ------------------------------------------------------------------
    # Onchanges and grid
    # ------------------------------------------------------------------
    @api.onchange("style_id")
    def _onchange_style_id(self):
        style = self.style_id
        if not style:
            return
        if style.buyer_id and not self.buyer_id:
            self.buyer_id = style.buyer_id
        self.techpack_id = style.current_techpack_id
        self.colour_ids = style.colour_ids
        self.size_ids = style.size_range_id.size_ids
        self._onchange_grid_axes()

    @api.onchange("colour_ids", "size_ids")
    def _onchange_grid_axes(self):
        colour_ids = set(self.colour_ids._origin.ids)
        size_ids = set(self.size_ids._origin.ids)
        keep = self.line_ids.filtered(
            lambda l: l.colour_id._origin.id in colour_ids and l.size_id._origin.id in size_ids)
        existing = {(l.colour_id._origin.id, l.size_id._origin.id) for l in keep}
        new_lines = self.env["garment.order.line"]
        for vals in self._grid_missing_vals(existing):
            new_lines |= new_lines.new(vals)
        self.line_ids = keep | new_lines

    def _grid_missing_vals(self, existing):
        """Values of the grid cells (colour × size) not yet in ``existing`` {(colour_id, size_id)}."""
        vals_list = []
        sizes = self.size_ids._origin.sorted(lambda s: (s.sequence, s.id))
        for c_index, colour in enumerate(self.colour_ids._origin.sorted("id")):
            for size in sizes:
                if (colour.id, size.id) not in existing:
                    vals_list.append({
                        "colour_id": colour.id,
                        "size_id": size.id,
                        "sequence": (c_index + 1) * 1000 + size.sequence,
                        "qty_ordered": 0,
                    })
        return vals_list

    def _sync_grid_lines(self):
        """Server-side twin of the onchange: make sure every colour × size cell has a line."""
        for order in self:
            existing = {(l.colour_id.id, l.size_id.id) for l in order.line_ids}
            missing = order._grid_missing_vals(existing)
            if missing:
                order.line_ids = [Command.create(v) for v in missing]

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].with_company(
                    vals.get("company_id") or self.env.company.id
                ).next_by_code("garment.order") or _("New")
            if vals.get("style_id"):
                style = self.env["garment.style"].browse(vals["style_id"])
                vals.setdefault("buyer_id", style.buyer_id.id)
                if "techpack_id" not in vals and style.current_techpack_id:
                    vals["techpack_id"] = style.current_techpack_id.id
                if "colour_ids" not in vals and not vals.get("line_ids"):
                    vals["colour_ids"] = [Command.set(style.colour_ids.ids)]
                if "size_ids" not in vals and not vals.get("line_ids"):
                    vals["size_ids"] = [Command.set(style.size_range_id.size_ids.ids)]
        orders = super().create(vals_list)
        orders._sync_grid_lines()
        return orders

    def write(self, vals):
        old_dates = {o.id: o.ex_factory_date for o in self} if "ex_factory_date" in vals else {}
        if "line_ids" in vals and not self.env.context.get("garment_progress_api"):
            for order in self:
                if order.state not in ("draft",) and not order.is_amending and not vals.get("is_amending"):
                    raise UserError(_("Order %s is confirmed: use Amend Order to change the grid.", order.name))
        res = super().write(vals)
        if "colour_ids" in vals or "size_ids" in vals:
            self._sync_grid_lines()
        if old_dates:
            for order in self:
                if old_dates.get(order.id) != order.ex_factory_date:
                    order._reschedule_milestones()
        return res

    def unlink(self):
        for order in self:
            if order.state not in ("draft", "cancel"):
                raise UserError(_("Only draft or cancelled production orders can be deleted (%s).", order.name))
        return super().unlink()

    # ------------------------------------------------------------------
    # State changes
    # ------------------------------------------------------------------
    def action_confirm(self):
        for order in self:
            if order.state != "draft":
                raise UserError(_("Only a draft order can be confirmed."))
            if order.qty_ordered <= 0:
                raise UserError(_("Enter the quantities in the size and colour grid before confirming %s.",
                                  order.name))
            if not order.style_id.approved_for_production:
                raise UserError(_("Style %s is not approved for production: its tech pack must be approved "
                                  "before the order is confirmed.", order.style_id.display_name))
            order.state = "confirmed"
            if order.tna_template_id and not order.milestone_ids:
                order.action_apply_tna_template()
        return True

    def action_start_production(self):
        for order in self:
            if order.state != "confirmed":
                raise UserError(_("Only a confirmed order can go into production."))
            order.state = "in_production"
        return True

    def action_mark_completed(self):
        for order in self:
            if order.state not in ("confirmed", "in_production", "packed", "shipped"):
                raise UserError(_("Only a running order can be marked completed."))
            if order.qty_shipped < order.qty_ordered:
                raise UserError(_("Order %(order)s still has %(qty)s pieces to ship. Use Close Order to close "
                                  "it short.", order=order.name, qty=order.qty_ordered - order.qty_shipped))
            order.state = "closed"
        return True

    def action_close(self):
        """Close an order short (balance not shipped). Factory Manager only; logged in chatter."""
        if not self.env.user.has_group("zyra_garment_base.group_garment_factory_manager"):
            raise UserError(_("Only a Factory Manager can close an order with pieces still to ship."))
        for order in self:
            if order.state in ("draft", "closed", "cancel"):
                raise UserError(_("Order %s is not running.", order.name))
            if order.qty_balance > 0:
                order.message_post(body=_("Closed short by %(user)s with %(qty)s pieces not shipped.",
                                          user=self.env.user.name, qty=order.qty_balance))
            order.state = "closed"
        return True

    def action_cancel(self):
        for order in self:
            if order.state not in ("draft", "confirmed"):
                raise UserError(_("Only a draft or confirmed order without production can be cancelled."))
            if order.progress_ids:
                raise UserError(_("Order %s already has production postings.", order.name))
            order.state = "cancel"
        return True

    def action_draft(self):
        for order in self:
            if order.state != "cancel":
                raise UserError(_("Only a cancelled order can be reset to draft."))
            order.state = "draft"
        return True

    def action_amend(self):
        for order in self:
            if order.state not in ("confirmed", "in_production", "packed"):
                raise UserError(_("Only a confirmed or running order can be amended."))
            order.is_amending = True
        return True

    def action_done_amending(self):
        for order in self:
            if order.is_amending:
                order.is_amending = False
                order.message_post(body=_("Order amended: %s pieces ordered.", order.qty_ordered))
        return True

    # ------------------------------------------------------------------
    # Progress API (contract for cutting, sewing, quality, packing, shipping)
    # ------------------------------------------------------------------
    def _garment_add_progress(self, stage, colour_id, size_id, qty, ref=None, date=None):
        """Add ``qty`` pieces to ``stage`` for one cell of the grid. See README "Progress API".

        :param stage: 'cut', 'sewn', 'packed' or 'shipped'
        :param colour_id: garment.colour id or record
        :param size_id: garment.size id or record
        :param qty: integer pieces, non-zero; negative reverses an earlier posting
        :param ref: optional text (bundle, lay, carton, shipment reference)
        :param date: optional datetime of the event (default now)
        :return: the created ``garment.order.progress`` record
        """
        self.ensure_one()
        if stage not in PROGRESS_STAGES:
            raise ValidationError(_("Unknown production stage %(stage)s; use one of %(stages)s.",
                                    stage=stage, stages=", ".join(PROGRESS_STAGES)))
        if isinstance(qty, float):
            if not qty.is_integer():
                raise ValidationError(_("Pieces must be a whole number (got %s).", qty))
            qty = int(qty)
        if not isinstance(qty, int) or isinstance(qty, bool) or qty == 0:
            raise ValidationError(_("Pieces to post must be a non-zero whole number."))
        if self.state not in ("confirmed", "in_production", "packed", "shipped"):
            raise UserError(_("Order %(order)s is %(state)s: production can only be posted on a confirmed, "
                              "running order.", order=self.name,
                              state=dict(self._fields["state"]._description_selection(self.env))[self.state]))
        colour_id = colour_id.id if isinstance(colour_id, models.BaseModel) else colour_id
        size_id = size_id.id if isinstance(size_id, models.BaseModel) else size_id
        line = self.line_ids.filtered(lambda l: l.colour_id.id == colour_id and l.size_id.id == size_id)
        if not line:
            raise UserError(_("Order %s has no grid cell for this colourway and size.", self.name))
        field = "qty_%s" % stage
        if line[field] + qty < 0:
            raise ValidationError(_("Posting %(qty)s %(stage)s would leave a negative quantity on %(cell)s.",
                                    qty=qty, stage=stage, cell=line.display_name))
        progress = self.env["garment.order.progress"].sudo().create({
            "order_id": self.id,
            "line_id": line.id,
            "stage": stage,
            "qty": qty,
            "ref": ref,
            "date": date or fields.Datetime.now(),
            "user_id": self.env.user.id,
        })
        self.sudo()._advance_state_from_progress()
        return progress.sudo(False)

    def _advance_state_from_progress(self):
        """Confirmed → in production on the first piece; → packed / shipped when the whole order is."""
        for order in self:
            if order.state == "confirmed" and (order.qty_cut or order.qty_sewn or order.qty_packed):
                order.state = "in_production"
            if order.state in ("confirmed", "in_production") and order.qty_ordered \
                    and order.qty_packed >= order.qty_ordered:
                order.state = "packed"
            if order.state in ("confirmed", "in_production", "packed") and order.qty_ordered \
                    and order.qty_shipped >= order.qty_ordered:
                order.state = "shipped"

    def _garment_get_grid(self):
        """Read helper: {(colour_id, size_id): {'ordered', 'cut', 'sewn', 'packed', 'shipped'}}."""
        self.ensure_one()
        return {
            (l.colour_id.id, l.size_id.id): {
                "ordered": l.qty_ordered, "cut": l.qty_cut, "sewn": l.qty_sewn,
                "packed": l.qty_packed, "shipped": l.qty_shipped,
            } for l in self.line_ids
        }

    # ------------------------------------------------------------------
    # Time and action
    # ------------------------------------------------------------------
    def action_apply_tna_template(self):
        for order in self:
            if not order.tna_template_id:
                raise UserError(_("Choose a T&A template first."))
            if order.milestone_ids.filtered("actual_date"):
                raise UserError(_("Milestones of %s already have actual dates; edit them by hand.", order.name))
            order.milestone_ids.unlink()
            order.milestone_ids = [Command.create({
                "name": tl.name,
                "sequence": tl.sequence,
                "days_before_ex_factory": tl.days_before_ex_factory,
                "planned_date": order.ex_factory_date - timedelta(days=tl.days_before_ex_factory),
                "owner_id": tl.owner_id.id or order.merchandiser_id.id,
                "template_line_id": tl.id,
            }) for tl in order.tna_template_id.line_ids]
        return True

    def _reschedule_milestones(self):
        """Ex-factory moved: open template milestones move with it."""
        for order in self:
            moved = order.milestone_ids.filtered(lambda m: not m.actual_date and m.template_line_id)
            for ms in moved:
                ms.planned_date = order.ex_factory_date - timedelta(days=ms.days_before_ex_factory)
            if moved:
                order.message_post(body=_("Ex-factory date moved to %(date)s: %(n)s open milestones rescheduled.",
                                          date=order.ex_factory_date, n=len(moved)))

    # ------------------------------------------------------------------
    # Smart buttons
    # ------------------------------------------------------------------
    def action_view_sale_order(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
        }

    def action_view_samples(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_sample")
        action["domain"] = [("order_id", "=", self.id)]
        action["context"] = {"default_order_id": self.id, "default_style_id": self.style_id.id}
        return action

    def action_view_milestones(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_tna_milestone")
        action["domain"] = [("order_id", "=", self.id)]
        action["context"] = {"default_order_id": self.id}
        return action

    def action_view_postings(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_order_progress")
        action["domain"] = [("order_id", "=", self.id)]
        return action

    def action_view_cost_sheet(self):
        self.ensure_one()
        sheet = self._get_approved_cost_sheet()
        if not sheet:
            return False
        return {"type": "ir.actions.act_window", "res_model": sheet._name, "res_id": sheet.id,
                "view_mode": "form"}
