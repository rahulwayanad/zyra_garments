from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

STYLE_STAGES = [
    ("draft", "Draft"),
    ("development", "In Development"),
    ("approved", "Approved for Production"),
]


class GarmentStyle(models.Model):
    _name = "garment.style"
    _description = "Garment Style"
    _inherit = ["mail.thread", "mail.activity.mixin", "image.mixin"]
    _order = "code desc, id desc"
    _rec_names_search = ["code", "name", "buyer_style_ref"]
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, tracking=True, copy=False, default=lambda self: _("New"))
    buyer_id = fields.Many2one(
        "res.partner", string="Buyer", tracking=True, index=True,
        domain="[('is_garment_buyer', '=', True)]")
    buyer_style_ref = fields.Char(string="Buyer's Style Ref.")
    season_id = fields.Many2one("garment.season", string="Season", tracking=True)
    collection = fields.Char()
    type_id = fields.Many2one("garment.type", string="Garment Type", tracking=True, index=True)
    fabric_kind = fields.Selection([("woven", "Woven"), ("knit", "Knit")], string="Fabric", default="woven")
    merchandiser_id = fields.Many2one("res.users", string="Merchandiser", default=lambda self: self.env.user)
    size_range_id = fields.Many2one("garment.size.range", string="Size Range", tracking=True)
    size_names = fields.Char(related="size_range_id.size_names", string="Sizes")
    colour_ids = fields.Many2many("garment.colour", string="Colourways")
    colour_count = fields.Integer(compute="_compute_colour_count")
    notes = fields.Html()

    product_tmpl_id = fields.Many2one(
        "product.template", string="Product", copy=False, check_company=True, ondelete="set null",
        help="The garment product. Its variants are colourway × size.")
    variant_count = fields.Integer(string="Variants", compute="_compute_variant_count")
    bom_id = fields.Many2one(related="current_techpack_id.bom_id", string="Odoo Bill of Materials")

    techpack_ids = fields.One2many("zyra.techpack", "style_id", string="Tech Packs")
    techpack_count = fields.Integer(string="Versions", compute="_compute_techpack_count")
    current_techpack_id = fields.Many2one(
        "zyra.techpack", string="Current Tech Pack", compute="_compute_current_techpack", store=True,
        help="Latest approved revision: the one production works to.")
    working_techpack_id = fields.Many2one(
        "zyra.techpack", string="Tech Pack Shown", compute="_compute_working_techpack",
        search="_search_working_techpack",
        help="The open revision if there is one, otherwise the current approved revision.")
    working_techpack_state = fields.Selection(related="working_techpack_id.state", string="Shown Revision Status")
    working_revision = fields.Integer(related="working_techpack_id.revision", string="Tech Pack Version")
    base_size_id = fields.Many2one(related="working_techpack_id.base_size_id", string="Base Size")
    approved_for_production = fields.Boolean(compute="_compute_current_techpack", store=True)
    stage = fields.Selection(STYLE_STAGES, compute="_compute_current_techpack", store=True, tracking=True,
                             string="Status")
    sam = fields.Float(string="SAM", digits=(16, 2), compute="_compute_current_techpack", store=True,
                       help="Standard allowed minutes per piece, from the current tech pack's operations.")
    material_cost = fields.Monetary(string="Material / pc", compute="_compute_material_cost",
                                    currency_field="currency_id")

    # The tabs of the style form show the lines of the working revision.
    bom_line_ids = fields.One2many(related="working_techpack_id.bom_line_ids", readonly=False, string="Materials")
    operation_ids = fields.One2many(related="working_techpack_id.operation_ids", readonly=False,
                                    string="Operation Bulletin")
    measurement_ids = fields.One2many(related="working_techpack_id.measurement_ids", readonly=False,
                                      string="Measurement Spec")
    construction_ids = fields.One2many(related="working_techpack_id.construction_ids", readonly=False,
                                       string="Construction")
    graded_chart_html = fields.Html(related="working_techpack_id.graded_chart_html")
    measure_unit = fields.Selection(related="working_techpack_id.measure_unit", readonly=False)
    artwork_note = fields.Html(related="working_techpack_id.artwork_note", readonly=False)
    label_note = fields.Html(related="working_techpack_id.label_note", readonly=False)
    packing_note = fields.Html(related="working_techpack_id.packing_note", readonly=False)
    attachment_ids = fields.Many2many(related="working_techpack_id.attachment_ids", readonly=False,
                                      string="Documents")

    company_id = fields.Many2one("res.company", required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)", "A style code must be unique per company."),
    ]

    # ------------------------------------------------------------------ computes
    @api.depends("colour_ids")
    def _compute_colour_count(self):
        for style in self:
            style.colour_count = len(style.colour_ids)

    @api.depends("product_tmpl_id.product_variant_count")
    def _compute_variant_count(self):
        for style in self:
            style.variant_count = style.product_tmpl_id.product_variant_count if style.product_tmpl_id else 0

    @api.depends("techpack_ids")
    def _compute_techpack_count(self):
        for style in self:
            style.techpack_count = len(style.techpack_ids)

    @api.depends("techpack_ids.state", "techpack_ids.revision", "techpack_ids.sam")
    def _compute_current_techpack(self):
        for style in self:
            approved = style.techpack_ids.filtered(lambda t: t.state == "approved").sorted("revision")
            current = approved[-1:] if approved else self.env["zyra.techpack"]
            style.current_techpack_id = current
            style.approved_for_production = bool(current)
            style.sam = current.sam
            if current:
                style.stage = "approved"
            elif style.techpack_ids:
                style.stage = "development"
            else:
                style.stage = "draft"

    @api.depends("techpack_ids.state", "current_techpack_id")
    def _compute_working_techpack(self):
        for style in self:
            open_rev = style.techpack_ids.filtered(lambda t: t.state in ("draft", "submitted"))
            style.working_techpack_id = open_rev[:1] or style.current_techpack_id or \
                style.techpack_ids.sorted("revision")[-1:]

    def _search_working_techpack(self, operator, value):
        if operator not in ("=", "in"):
            return NotImplemented
        ids = [value] if isinstance(value, int) else list(value or [])
        techpacks = self.env["zyra.techpack"].browse([i for i in ids if i])
        styles = techpacks.style_id.filtered(lambda s: s.working_techpack_id in techpacks)
        return [("id", "in", styles.ids)]

    @api.depends("current_techpack_id.material_cost", "working_techpack_id.material_cost")
    def _compute_material_cost(self):
        for style in self:
            style.material_cost = (style.current_techpack_id or style.working_techpack_id).material_cost

    # ------------------------------------------------------------------ constraints
    @api.constrains("size_range_id", "colour_ids")
    def _check_spec_against_techpacks(self):
        for style in self:
            for line in style.techpack_ids.bom_line_ids:
                if line.size_id and line.size_id.range_id != style.size_range_id:
                    raise ValidationError(_(
                        "Style %(style)s: size %(size)s used in tech pack %(tp)s is not in the size range.",
                        style=style.code, size=line.size_id.name, tp=line.techpack_id.name))

    def write(self, vals):
        if "size_range_id" in vals:
            for style in self:
                if style.size_range_id.id != vals["size_range_id"] and style.techpack_ids.filtered(
                        lambda t: t.state in ("approved", "superseded")):
                    raise UserError(_(
                        "Style %s has an approved tech pack: its size range can no longer change. "
                        "Copy the tech pack to a new style instead.", style.code))
        return super().write(vals)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for style in self:
            style.display_name = f"[{style.code}] {style.name}" if style.code else style.name

    # ------------------------------------------------------------------ actions
    def action_new_techpack(self):
        """Create the first (or next) revision of the tech pack."""
        self.ensure_one()
        if self.current_techpack_id:
            return self.current_techpack_id.action_new_revision()
        techpack = self.env["zyra.techpack"].sudo().create({"style_id": self.id})
        return techpack._get_form_action()

    def action_new_version(self):
        self.ensure_one()
        source = self.current_techpack_id or self.techpack_ids.sorted("revision")[-1:]
        if not source:
            return self.action_new_techpack()
        return source.action_new_revision()

    def action_copy_techpack(self):
        """Start a new style from this one: same header, a draft v1 copied from the current tech pack."""
        self.ensure_one()
        source = self.current_techpack_id or self.working_techpack_id
        new_style = self.copy({
            "name": _("%s (copy)", self.name),
            "code": _("%s-COPY", self.code),
        })
        if source:
            source._copy_to_style(new_style)
        return {
            "type": "ir.actions.act_window",
            "res_model": "garment.style",
            "res_id": new_style.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print_techpack(self):
        self.ensure_one()
        techpack = self.working_techpack_id
        if not techpack:
            raise UserError(_("Style %s has no tech pack to print yet.", self.code))
        return self.env.ref("zyra_techpack.action_report_techpack").report_action(techpack)

    def action_generate_variants_bom(self):
        """Create / update the garment product (colourway × size) and the BoM of the current tech pack."""
        for style in self:
            style._ensure_product()
            if style.current_techpack_id:
                style.current_techpack_id._generate_bom()
        return True

    def action_view_variants(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("product.product_normal_action_sell")
        action["domain"] = [("product_tmpl_id", "=", self.product_tmpl_id.id)]
        action["context"] = {"create": False}
        return action

    def action_view_techpacks(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_techpack.action_zyra_techpack")
        action["domain"] = [("style_id", "=", self.id)]
        action["context"] = {"default_style_id": self.id}
        return action

    # ------------------------------------------------------------------ product / variants
    def _get_colour_attribute(self):
        attribute = self.env["product.attribute"].search([("garment_role", "=", "colour")], limit=1)
        if not attribute:
            attribute = self.env["product.attribute"].create({
                "name": _("Colour"), "garment_role": "colour", "create_variant": "always",
                "display_type": "color",
            })
        return attribute

    def _get_size_attribute(self):
        self.ensure_one()
        size_range = self.size_range_id
        attribute = self.env["product.attribute"].search([
            ("garment_role", "=", "size"), ("garment_size_range_id", "=", size_range.id)], limit=1)
        if not attribute:
            attribute = self.env["product.attribute"].create({
                "name": _("Size (%s)", size_range.name), "garment_role": "size",
                "garment_size_range_id": size_range.id, "create_variant": "always",
            })
        return attribute

    def _get_attribute_values(self):
        """Return (colour values, size values) for this style's colourways and size range."""
        self.ensure_one()
        Value = self.env["product.attribute.value"]
        colour_attr = self._get_colour_attribute()
        size_attr = self._get_size_attribute()
        colour_values = Value
        for colour in self.colour_ids:
            value = Value.search([("attribute_id", "=", colour_attr.id), ("garment_colour_id", "=", colour.id)],
                                 limit=1)
            if not value:
                name = colour.name
                if Value.search_count([("attribute_id", "=", colour_attr.id), ("name", "=", name)]):
                    name = f"{colour.name} ({colour.code or colour.id})"
                value = Value.create({"attribute_id": colour_attr.id, "name": name,
                                      "garment_colour_id": colour.id, "html_color": colour.hex or False})
            colour_values |= value
        size_values = Value
        for size in self.size_range_id.size_ids.sorted(lambda s: (s.sequence, s.id)):
            value = Value.search([("attribute_id", "=", size_attr.id), ("garment_size_id", "=", size.id)], limit=1)
            if not value:
                value = Value.create({"attribute_id": size_attr.id, "name": size.name,
                                      "garment_size_id": size.id, "sequence": size.sequence})
            size_values |= value
        return colour_values, size_values

    def _ensure_product(self):
        """Create or update the product template: one variant per colourway × size."""
        self.ensure_one()
        if not self.colour_ids or not self.size_range_id.size_ids:
            raise UserError(_("Style %s needs colourways and a size range before variants can be made.",
                              self.code))
        colour_values, size_values = self._get_attribute_values()
        template = self.product_tmpl_id
        if not template:
            routes = self.env["stock.route"]
            manufacture = self.env.ref("mrp.route_warehouse0_manufacture", raise_if_not_found=False)
            if manufacture:
                routes |= manufacture
            mto = self.env.ref("stock.route_warehouse0_mto", raise_if_not_found=False)
            if mto and mto.active:
                routes |= mto
            template = self.env["product.template"].create({
                "name": self.name,
                "default_code": self.code,
                "type": "consu",
                "is_storable": True,
                "sale_ok": True,
                "purchase_ok": False,
                "garment_style_id": self.id,
                "company_id": self.company_id.id,
                "route_ids": [Command.set(routes.ids)],
                "image_1920": self.image_1920,
            })
            self.product_tmpl_id = template
        commands = []
        for values in (colour_values, size_values):
            attribute = values.attribute_id
            line = template.attribute_line_ids.filtered(lambda ln, a=attribute: ln.attribute_id == a)
            if line:
                missing = values - line.value_ids
                if missing:
                    commands.append(Command.update(line.id, {"value_ids": [Command.link(v.id) for v in missing]}))
            else:
                commands.append(Command.create({"attribute_id": attribute.id,
                                                "value_ids": [Command.set(values.ids)]}))
        if commands:
            template.write({"attribute_line_ids": commands})
        return template

    def _get_variant(self, colour, size):
        """The product variant of this style for one colourway and size (empty recordset if none)."""
        self.ensure_one()
        variants = self.product_tmpl_id.product_variant_ids
        return variants.filtered(lambda p: p.garment_colour_id == colour and p.garment_size_id == size)[:1]
