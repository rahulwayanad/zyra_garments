from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_round

STATES = [
    ("draft", "Draft"),
    ("submitted", "Awaiting Approval"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("superseded", "Superseded"),
]


class GarmentCostSheet(models.Model):
    """Price build-up of one style, from one tech pack revision, for one buyer.

    A sheet *family* shares one number (``name``, e.g. CS/2026/0008); every
    "New Version" adds a row with ``version`` + 1. Approving a version supersedes
    the version approved before it.
    """

    _name = "garment.cost.sheet"
    _description = "Garment Cost Sheet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "costing_date desc, name desc, version desc, id desc"
    _check_company_auto = True

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name = fields.Char(
        string="Sheet No.", required=True, copy=False, readonly=True, index=True,
        default=lambda self: _("New"),
    )
    version = fields.Integer(string="Ver.", default=1, required=True, copy=False, readonly=True)
    is_latest = fields.Boolean(
        string="Latest Version", compute="_compute_is_latest", search="_search_is_latest",
    )
    company_id = fields.Many2one(
        "res.company", required=True, index=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency")
    state = fields.Selection(
        STATES, default="draft", required=True, tracking=True, copy=False, index=True,
    )

    techpack_id = fields.Many2one(
        "zyra.techpack", string="Tech Pack Revision", required=True, tracking=True,
        index=True, ondelete="restrict",
    )
    style_id = fields.Many2one(
        "garment.style", related="techpack_id.style_id", store=True, index=True, string="Style",
    )
    style_label = fields.Char(string="Style ", compute="_compute_style_label")
    buyer_id = fields.Many2one(
        "res.partner", string="Buyer", tracking=True, domain="[('is_garment_buyer', '=', True)]",
        compute="_compute_buyer_id", store=True, readonly=False, precompute=True,
    )
    production_order_ref = fields.Char(
        string="Production Order", compute="_compute_production_order_ref",
        help="Production order of this style (shown when Merchandising is installed).",
    )
    quantity_basis = fields.Integer(
        string="Quantity Basis", default=1000, tracking=True,
        help="Pieces the price is quoted for; per-order costs are spread over this quantity.",
    )
    buyer_supplies_fabric = fields.Boolean(
        string="Buyer Supplies the Fabric", tracking=True,
        help="CMT: fabric is supplied by the buyer and left out of the price.",
    )
    costing_date = fields.Date(string="Costing Date", default=fields.Date.context_today, required=True)
    user_id = fields.Many2one(
        "res.users", string="Costed By", default=lambda self: self.env.user, tracking=True,
    )

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------
    material_line_ids = fields.One2many("garment.cost.sheet.material", "sheet_id", string="Materials", copy=True)
    fabric_line_ids = fields.One2many(
        "garment.cost.sheet.material", "sheet_id", string="Fabric",
        domain=[("material_kind", "=", "fabric")],
    )
    trim_line_ids = fields.One2many(
        "garment.cost.sheet.material", "sheet_id", string="Trims",
        domain=[("material_kind", "in", ("trim", "packing"))],
    )
    process_line_ids = fields.One2many("garment.cost.sheet.process", "sheet_id", string="Processes", copy=True)
    version_ids = fields.One2many(
        "garment.cost.sheet", compute="_compute_version_ids", string="Versions",
    )

    # ------------------------------------------------------------------
    # Making cost
    # ------------------------------------------------------------------
    sam = fields.Float(
        string="SAM (min)", digits=(16, 2), tracking=True,
        compute="_compute_sam", store=True, readonly=False, precompute=True,
    )
    line_efficiency = fields.Float(
        string="Line Efficiency %", digits=(16, 2), tracking=True,
        default=lambda self: self.env.company.target_efficiency,
        help="Percent: 62.0 means 62 %.",
    )
    cost_per_minute = fields.Float(
        string="Cost per Minute", digits=(16, 4), tracking=True,
        default=lambda self: self.env.company.minute_value,
    )
    making_cost_pc = fields.Monetary(string="Making Cost / pc", compute="_compute_costs", store=True)

    # ------------------------------------------------------------------
    # Shares of the FOB price
    # ------------------------------------------------------------------
    overhead_pct = fields.Float(string="Commercial and Finance %", digits=(16, 2), default=3.0, tracking=True)
    commission_pct = fields.Float(string="Commission %", digits=(16, 2), tracking=True)
    margin_pct = fields.Float(string="Margin %", digits=(16, 2), default=15.0, tracking=True)
    freight_pc = fields.Monetary(string="Freight / pc", tracking=True)
    margin_floor_pct = fields.Float(
        string="Margin Floor %", digits=(16, 2), readonly=True, copy=False,
        default=lambda self: self.env.company.margin_floor_pct,
        help="Company margin floor when the sheet was costed.",
    )
    below_floor = fields.Boolean(string="Below Floor", compute="_compute_below_floor", store=True)

    # ------------------------------------------------------------------
    # Totals per piece
    # ------------------------------------------------------------------
    fabric_cost_pc = fields.Monetary(string="Fabric / pc", compute="_compute_costs", store=True)
    trim_cost_pc = fields.Monetary(string="Trims / pc", compute="_compute_costs", store=True)
    material_cost_pc = fields.Monetary(string="Material / pc", compute="_compute_costs", store=True)
    process_cost_pc = fields.Monetary(string="Processes / pc", compute="_compute_costs", store=True)
    total_cost_pc = fields.Monetary(
        string="Cost / pc", compute="_compute_costs", store=True,
        help="Material + processes + making, before overheads, commission and margin.",
    )
    overhead_amount_pc = fields.Monetary(string="Commercial and Finance / pc", compute="_compute_costs", store=True)
    commission_amount_pc = fields.Monetary(string="Commission / pc", compute="_compute_costs", store=True)
    margin_amount_pc = fields.Monetary(string="Margin / pc", compute="_compute_costs", store=True)

    # ------------------------------------------------------------------
    # Price
    # ------------------------------------------------------------------
    target_price = fields.Monetary(string="Target Price", tracking=True)
    fob_price = fields.Monetary(string="FOB Price", compute="_compute_costs", store=True, tracking=True)
    fob_over_target = fields.Monetary(string="FOB over Target", compute="_compute_costs", store=True)
    cif_price = fields.Monetary(string="CIF Price", compute="_compute_costs", store=True)
    quoted_value = fields.Monetary(string="Quoted Value", compute="_compute_costs", store=True)
    material_share_pct = fields.Float(string="Material Share %", compute="_compute_costs", store=True, digits=(16, 1))

    # ------------------------------------------------------------------
    # Approval
    # ------------------------------------------------------------------
    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True, copy=False)
    approved_date = fields.Date(string="Approved On", readonly=True, copy=False)
    floor_override_reason = fields.Text(
        string="Reason for Approval below Floor", readonly=True, copy=False, tracking=True,
    )
    sale_order_ids = fields.Many2many("sale.order", string="Quotations", copy=False, readonly=True)
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")
    notes = fields.Html(string="Notes")

    _sql_constraints = [
        ("name_version_company_unique", "unique(name, version, company_id)",
         "A cost sheet version can exist only once."),
    ]

    # ==================================================================
    # Formulas (kept as plain class methods so tests can check numbers)
    # ==================================================================
    @api.model
    def _formula_making_cost(self, sam, cost_per_minute, efficiency_pct):
        """Making cost / pc = SAM x cost per minute / (line efficiency / 100)."""
        if not efficiency_pct:
            return 0.0
        return sam * cost_per_minute / (efficiency_pct / 100.0)

    @api.model
    def _formula_fob_price(self, cost_pc, overhead_pct, commission_pct, margin_pct):
        """FOB = cost / (1 - (overheads % + commission % + margin %) / 100).

        Overheads, commission and margin are shares *of the FOB price*, so the
        cost is grossed up rather than marked up.
        """
        shares = (overhead_pct + commission_pct + margin_pct) / 100.0
        if shares >= 1.0:
            return 0.0
        return cost_pc / (1.0 - shares)

    @api.model
    def _formula_margin_at_price(self, cost_pc, overhead_pct, commission_pct, price):
        """Margin % left at a given price = 100 - overheads % - commission % - cost / price x 100."""
        if not price:
            return 0.0
        return 100.0 - overhead_pct - commission_pct - cost_pc / price * 100.0

    @api.model
    def _formula_material_cost_pc(self, consumption, wastage_pct, price_unit, share_pct):
        """Material cost / pc = consumption x (1 + wastage %) x price x share of the order %."""
        return consumption * (1.0 + wastage_pct / 100.0) * price_unit * share_pct / 100.0

    @api.model
    def _formula_process_cost_pc(self, cost, charge_basis, quantity_basis):
        """Per piece costs stay as they are; a cost for the whole order is spread over the quantity basis."""
        if charge_basis == "order":
            return cost / quantity_basis if quantity_basis else 0.0
        return cost

    # ==================================================================
    # Computes
    # ==================================================================
    def _family_max_versions(self, names=None):
        domain = [("name", "in", list(names))] if names is not None else []
        groups = self.with_context(active_test=False)._read_group(
            domain, ["name", "company_id"], ["version:max"])
        return {(name, company.id): version for name, company, version in groups}

    @api.depends("name", "company_id", "version")
    def _compute_is_latest(self):
        maxima = self._family_max_versions({n for n in self.mapped("name") if n})
        for sheet in self:
            sheet.is_latest = sheet.version >= maxima.get((sheet.name, sheet.company_id.id), 0)

    def _search_is_latest(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise UserError(_("Unsupported search on the latest version."))
        maxima = self._family_max_versions()
        ids = [
            sheet.id for sheet in self.search_fetch([], ["name", "company_id", "version"])
            if sheet.version >= maxima.get((sheet.name, sheet.company_id.id), 0)
        ]
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", ids)]

    @api.depends("style_id")
    def _compute_style_label(self):
        for sheet in self:
            style = sheet.style_id
            sheet.style_label = f"[{style.code}] {style.name}" if style else False

    @api.depends("techpack_id")
    def _compute_buyer_id(self):
        for sheet in self:
            if not sheet.buyer_id and sheet.techpack_id.style_id.buyer_id:
                sheet.buyer_id = sheet.techpack_id.style_id.buyer_id

    @api.depends("techpack_id")
    def _compute_sam(self):
        for sheet in self:
            if sheet.techpack_id and not sheet.sam:
                sheet.sam = sheet.techpack_id.sam or sheet.techpack_id.style_id.sam

    def _compute_production_order_ref(self):
        """Soft link to zyra_garment_merch: show the production order(s) of the style."""
        Order = self.env.get("garment.order")
        can_read = Order is not None and "style_id" in Order._fields and Order.has_access("read")
        for sheet in self:
            ref = False
            if can_read and sheet.style_id:
                domain = [("style_id", "=", sheet.style_id.id)]
                if "techpack_id" in Order._fields:
                    domain = [("techpack_id", "=", sheet.techpack_id.id)]
                if sheet.buyer_id and "buyer_id" in Order._fields:
                    domain.append(("buyer_id", "=", sheet.buyer_id.id))
                orders = Order.search(domain, limit=3)
                ref = ", ".join(orders.mapped("display_name")) or False
            sheet.production_order_ref = ref

    @api.depends(
        "buyer_supplies_fabric", "quantity_basis", "sam", "line_efficiency", "cost_per_minute",
        "overhead_pct", "commission_pct", "margin_pct", "freight_pc", "target_price",
        "material_line_ids.cost_pc", "material_line_ids.material_kind",
        "process_line_ids.cost_pc",
    )
    def _compute_costs(self):
        for sheet in self:
            parts = sheet._cost_parts()
            fabric, trims, processes, making, total, fob = (
                parts[k] for k in ("fabric", "trims", "processes", "making", "total", "fob"))
            sheet.fabric_cost_pc = fabric
            sheet.trim_cost_pc = trims
            sheet.material_cost_pc = fabric + trims
            sheet.process_cost_pc = processes
            sheet.making_cost_pc = making
            sheet.total_cost_pc = total
            sheet.fob_price = fob
            sheet.overhead_amount_pc = fob * sheet.overhead_pct / 100.0
            sheet.commission_amount_pc = fob * sheet.commission_pct / 100.0
            sheet.margin_amount_pc = fob * sheet.margin_pct / 100.0
            sheet.fob_over_target = fob - sheet.target_price if sheet.target_price else 0.0
            sheet.cif_price = fob + sheet.freight_pc
            # Quoted value uses the price as quoted (rounded to the currency).
            sheet.quoted_value = sheet.currency_id.round(fob) * sheet.quantity_basis if sheet.currency_id \
                else fob * sheet.quantity_basis
            sheet.material_share_pct = (fabric + trims) / fob * 100.0 if fob else 0.0

    def _cost_parts(self, **overrides):
        """Unrounded cost build-up per piece; ``overrides`` replace sheet inputs (What If)."""
        self.ensure_one()
        get = lambda name: overrides[name] if name in overrides else self[name]  # noqa: E731
        lines = self.material_line_ids
        fabric = 0.0 if self.buyer_supplies_fabric else sum(
            lines.filtered(lambda l: l.material_kind == "fabric").mapped("cost_pc"))
        trims = sum(lines.filtered(lambda l: l.material_kind != "fabric").mapped("cost_pc"))
        processes = sum(self.process_line_ids.mapped("cost_pc"))
        making = self._formula_making_cost(get("sam"), get("cost_per_minute"), get("line_efficiency"))
        total = fabric + trims + processes + making
        fob = self._formula_fob_price(total, get("overhead_pct"), get("commission_pct"), get("margin_pct"))
        return {"fabric": fabric, "trims": trims, "processes": processes, "making": making,
                "total": total, "fob": fob}

    @api.depends("margin_pct", "margin_floor_pct")
    def _compute_below_floor(self):
        for sheet in self:
            sheet.below_floor = float_compare(sheet.margin_pct, sheet.margin_floor_pct, precision_digits=2) < 0

    def _compute_version_ids(self):
        for sheet in self:
            if isinstance(sheet.id, int) and sheet.name:
                sheet.version_ids = self.search([
                    ("name", "=", sheet.name), ("company_id", "=", sheet.company_id.id),
                ], order="version desc")
            else:
                sheet.version_ids = False

    def _compute_sale_order_count(self):
        for sheet in self:
            sheet.sale_order_count = len(sheet.sale_order_ids)

    @api.depends("name", "version", "style_id")
    def _compute_display_name(self):
        for sheet in self:
            parts = [sheet.name or _("New")]
            if sheet.style_id.code:
                parts.append(sheet.style_id.code)
            parts.append(f"v{sheet.version}")
            sheet.display_name = " · ".join(parts)

    # ==================================================================
    # Constraints
    # ==================================================================
    @api.constrains("overhead_pct", "commission_pct", "margin_pct")
    def _check_shares(self):
        for sheet in self:
            if min(sheet.overhead_pct, sheet.commission_pct) < 0:
                raise ValidationError(_("Commercial, finance and commission shares cannot be negative."))
            if sheet.overhead_pct + sheet.commission_pct + sheet.margin_pct >= 100.0:
                raise ValidationError(_(
                    "Commercial and finance %, commission % and margin % together must stay under 100 %, "
                    "because they are shares of the FOB price."))

    @api.constrains("line_efficiency", "quantity_basis", "sam", "cost_per_minute")
    def _check_making_inputs(self):
        for sheet in self:
            if sheet.line_efficiency <= 0 or sheet.line_efficiency > 150:
                raise ValidationError(_("Line efficiency must be a percentage above 0 (for example 62 for 62 %)."))
            if sheet.quantity_basis <= 0:
                raise ValidationError(_("The quantity basis must be at least one piece."))
            if sheet.sam < 0 or sheet.cost_per_minute < 0:
                raise ValidationError(_("SAM and cost per minute cannot be negative."))

    # ==================================================================
    # CRUD
    # ==================================================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code(
                    "garment.cost.sheet", sequence_date=vals.get("costing_date")) or _("New")
        sheets = super().create(vals_list)
        self.invalidate_model(["version_ids", "is_latest"])
        if not self.env.context.get("garment_cost_sheet_no_load"):
            for sheet in sheets.filtered(lambda s: not s.material_line_ids and s.state == "draft"):
                lines = sheet._prepare_material_lines_from_techpack()
                if lines:
                    sheet.material_line_ids = [Command.create(v) for v in lines]
        return sheets

    def write(self, vals):
        locked = {"material_line_ids", "fabric_line_ids", "trim_line_ids", "process_line_ids",
                  "sam", "line_efficiency", "cost_per_minute", "overhead_pct", "commission_pct",
                  "margin_pct", "freight_pc", "target_price", "quantity_basis", "buyer_supplies_fabric",
                  "techpack_id"}
        if locked & set(vals) and not self.env.context.get("garment_cost_sheet_force"):
            if any(sheet.state in ("approved", "superseded") for sheet in self):
                raise UserError(_(
                    "An approved cost sheet cannot change. Make a new version instead."))
        return super().write(vals)

    def unlink(self):
        if any(sheet.state in ("approved", "superseded") for sheet in self):
            raise UserError(_("Approved or superseded cost sheets cannot be deleted."))
        return super().unlink()

    # ==================================================================
    # Tech pack loading
    # ==================================================================
    def _material_price(self, bom_line):
        """BoM price, else the first vendor price (purchase), else the product cost."""
        if bom_line.price_unit:
            return bom_line.price_unit
        product = bom_line.product_id
        seller = product.seller_ids.filtered(
            lambda s: not s.product_id or s.product_id == product)[:1]
        if seller:
            return seller.price
        return product.standard_price

    def _prepare_material_lines_from_techpack(self):
        """One line per (material, colourway) of the tech pack BoM.

        Lines that differ by size are averaged (equal weight per size). A colourway
        line gets an equal share of the order across the style's colourways; a line
        for all colourways gets 100 %.
        """
        self.ensure_one()
        techpack = self.techpack_id
        colours = techpack.style_id.colour_ids
        groups = {}
        for bl in techpack.bom_line_ids:
            key = (bl.product_id.id, bl.colour_id.id)
            groups.setdefault(key, []).append(bl)
        vals_list = []
        for (_product_id, colour_id), lines in groups.items():
            first = lines[0]
            n = len(lines)
            share = 100.0
            if colour_id and colours:
                share = float_round(100.0 / len(colours), precision_digits=2)
            vals_list.append({
                "method": "techpack",
                "material_kind": first.material_kind or "trim",
                "product_id": first.product_id.id,
                "colour_id": colour_id or False,
                "consumption": sum(l.consumption for l in lines) / n,
                "uom_id": first.uom_id.id or first.product_id.uom_id.id,
                "wastage_pct": sum(l.wastage_pct for l in lines) / n,
                "price_unit": sum(self._material_price(l) for l in lines) / n,
                "share_pct": share,
            })
        return vals_list

    def action_load_from_techpack(self):
        """Replace tech-pack lines with the current BoM of the tech pack revision; manual lines stay."""
        for sheet in self:
            if sheet.state != "draft":
                raise UserError(_("Only a draft cost sheet can be reloaded from the tech pack."))
            commands = [Command.unlink(l.id) for l in sheet.material_line_ids if l.method == "techpack"]
            commands += [Command.create(v) for v in sheet._prepare_material_lines_from_techpack()]
            sheet.write({
                "material_line_ids": commands,
                "sam": sheet.techpack_id.sam or sheet.sam,
            })
        return True

    # ==================================================================
    # Workflow
    # ==================================================================
    def _is_costing_approver(self):
        user = self.env.user
        return user.has_group("zyra_garment_base.group_garment_costing") or \
            user.has_group("zyra_garment_base.group_garment_factory_manager")

    def action_submit(self):
        for sheet in self:
            if sheet.state not in ("draft", "rejected"):
                raise UserError(_("Only a draft cost sheet can be sent for approval."))
            if not sheet.material_line_ids and not sheet.buyer_supplies_fabric:
                raise UserError(_("Add the materials before sending %s for approval.", sheet.display_name))
        self.write({"state": "submitted"})
        return True

    def action_approve(self):
        """Approve; a sheet under the margin floor opens the reason wizard (Factory Manager only)."""
        below = self.filtered("below_floor")
        if below and not self.env.context.get("garment_floor_reason"):
            if len(self) > 1:
                raise UserError(_("Approve cost sheets below the margin floor one at a time, with a reason."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Approve below the Margin Floor"),
                "res_model": "garment.cost.sheet.approve.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {"default_sheet_id": self.id},
            }
        self._do_approve(reason=self.env.context.get("garment_floor_reason"))
        return True

    def _do_approve(self, reason=None):
        for sheet in self:
            if sheet.state != "submitted":
                raise UserError(_("Only a cost sheet awaiting approval can be approved."))
            if not sheet._is_costing_approver():
                raise AccessError(_("Only Costing or a Factory Manager can approve cost sheets."))
            if sheet.below_floor:
                if not self.env.user.has_group("zyra_garment_base.group_garment_factory_manager"):
                    raise AccessError(_(
                        "%(sheet)s has a margin of %(margin).1f %%, under the %(floor).1f %% floor: "
                        "only a Factory Manager can approve it.",
                        sheet=sheet.display_name, margin=sheet.margin_pct, floor=sheet.margin_floor_pct))
                if not (reason or "").strip():
                    raise UserError(_("Give the reason for approving below the margin floor."))
        for sheet in self:
            previous = self.search([
                ("name", "=", sheet.name), ("company_id", "=", sheet.company_id.id),
                ("state", "=", "approved"), ("id", "!=", sheet.id),
            ])
            vals = {
                "state": "approved",
                "approved_by_id": self.env.uid,
                "approved_date": fields.Date.context_today(self),
            }
            if sheet.below_floor:
                vals["floor_override_reason"] = reason.strip()
            sheet.write(vals)
            if previous:
                previous.write({"state": "superseded"})
                for old in previous:
                    old.message_post(body=_("Superseded by version %s.", sheet.version))
            if sheet.below_floor:
                sheet.message_post(body=_(
                    "Approved below the margin floor (%(margin)s%% against %(floor)s%%): %(reason)s",
                    margin=f"{sheet.margin_pct:.1f}", floor=f"{sheet.margin_floor_pct:.1f}",
                    reason=reason.strip()))
            sheet._write_planned_cost_on_techpack()
        return True

    def _write_planned_cost_on_techpack(self):
        for sheet in self:
            techpacks = sheet.techpack_id
            # The style's other revisions that pointed at an older version of this family follow too.
            techpacks |= self.env["zyra.techpack"].search([
                ("approved_cost_sheet_id.name", "=", sheet.name),
                ("approved_cost_sheet_id.company_id", "=", sheet.company_id.id),
            ])
            techpacks.sudo().write({"approved_cost_sheet_id": sheet.id})

    def action_reject(self):
        for sheet in self:
            if sheet.state != "submitted":
                raise UserError(_("Only a cost sheet awaiting approval can be rejected."))
            if not sheet._is_costing_approver():
                raise AccessError(_("Only Costing or a Factory Manager can reject cost sheets."))
        self.write({"state": "rejected"})
        return True

    def action_reset_draft(self):
        for sheet in self:
            if sheet.state not in ("submitted", "rejected"):
                raise UserError(_("Only a submitted or rejected cost sheet goes back to draft."))
        self.write({"state": "draft"})
        return True

    def action_new_version(self):
        """Copy this version as version + 1 (draft) on the style's current tech pack revision."""
        self.ensure_one()
        latest = self.search([("name", "=", self.name), ("company_id", "=", self.company_id.id)],
                             order="version desc", limit=1)
        if latest != self:
            raise UserError(_("Make the new version from the latest one (version %s).", latest.version))
        if latest.state in ("draft", "submitted"):
            raise UserError(_("Version %s is still open: finish or reject it first.", latest.version))
        techpack = self.style_id.current_techpack_id or self.techpack_id
        new = self.with_context(garment_cost_sheet_force=True).copy({
            "name": self.name,
            "version": self.version + 1,
            "techpack_id": techpack.id,
            "costing_date": fields.Date.context_today(self),
            "user_id": self.env.uid,
        })
        new.message_post(body=_("New version of %(name)s, copied from version %(v)s.",
                                name=self.name, v=self.version))
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": new.id,
            "view_mode": "form",
            "target": "current",
        }

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default)
        if "name" not in default:
            for vals in vals_list:
                vals["name"] = _("New")
                vals["version"] = 1
        return vals_list

    def action_what_if(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("What If"),
            "res_model": "garment.cost.sheet.whatif",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sheet_id": self.id},
        }

    def action_create_quotation(self):
        """Quotation for the buyer: the style's garment product, quantity basis at the FOB price."""
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved cost sheet can be quoted."))
        if not self.buyer_id:
            raise UserError(_("Set the buyer first."))
        template = self.style_id.product_tmpl_id
        if not template and self.style_id.colour_ids and self.style_id.size_range_id.size_ids:
            self.style_id.sudo()._ensure_product()
            template = self.style_id.product_tmpl_id
        product = template.product_variant_ids[:1]
        if not product:
            raise UserError(_("Style %s has no garment product yet.", self.style_label))
        order = self.env["sale.order"].create({
            "partner_id": self.buyer_id.id,
            "company_id": self.company_id.id,
            "origin": self.display_name,
            "order_line": [Command.create({
                "product_id": product.id,
                "name": f"{self.style_label} — {self.display_name}",
                "product_uom_qty": self.quantity_basis,
                "price_unit": self.currency_id.round(self.fob_price),
            })],
        })
        self.sale_order_ids = [Command.link(order.id)]
        self.message_post(body=_("Quotation %s created.", order.name))
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_quotations(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_quotations_with_onboarding")
        action["domain"] = [("id", "in", self.sale_order_ids.ids)]
        action["context"] = {}
        return action

    def action_print(self):
        return self.env.ref("zyra_garment_costing.action_report_cost_sheet").report_action(self)
