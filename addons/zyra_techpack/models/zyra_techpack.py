from collections import defaultdict

from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

TECHPACK_STATES = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("approved", "Approved"),
    ("superseded", "Superseded"),
]
OPEN_STATES = ("draft", "submitted")
LOCKED_STATES = ("approved", "superseded")

GROUP_DESIGNER = "zyra_garment_base.group_garment_techpack_designer"
GROUP_MERCHANDISER = "zyra_garment_base.group_garment_merchandiser"
GROUP_MANAGER = "zyra_garment_base.group_garment_factory_manager"


class ZyraTechpack(models.Model):
    _name = "zyra.techpack"
    _description = "Tech Pack Revision"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "style_id, revision desc"
    _check_company_auto = True
    _mail_post_access = "read"  # merchandisers (read-only) comment and submit

    # Spec fields that are frozen once a revision is approved. Other modules may add their own fields
    # (e.g. a planned cost) and write them on an approved revision.
    _LOCKED_FIELDS = {
        "style_id", "revision", "base_size_id", "measure_unit", "bom_line_ids", "measurement_ids",
        "construction_ids", "operation_ids", "artwork_note", "label_note", "packing_note",
    }

    name = fields.Char(compute="_compute_name", store=True)
    style_id = fields.Many2one("garment.style", string="Style", required=True, ondelete="cascade", index=True,
                               check_company=True)
    revision = fields.Integer(default=0, copy=False, readonly=True,
                              help="1, 2, … per style; set automatically on creation.")
    state = fields.Selection(TECHPACK_STATES, default="draft", required=True, tracking=True, copy=False,
                             index=True)
    change_note = fields.Text(string="What Changed", help="Why this revision was made.")

    buyer_id = fields.Many2one(related="style_id.buyer_id", store=True)
    season_id = fields.Many2one(related="style_id.season_id")
    type_id = fields.Many2one(related="style_id.type_id", store=True)
    size_range_id = fields.Many2one(related="style_id.size_range_id")
    colour_ids = fields.Many2many(related="style_id.colour_ids")
    image_1920 = fields.Image(related="style_id.image_1920")
    base_size_id = fields.Many2one("garment.size", string="Base Size", tracking=True,
                                   domain="[('range_id', '=', size_range_id)]")
    measure_unit = fields.Selection([("cm", "Centimetres"), ("inch", "Inches")], string="Measured in",
                                    default="cm", required=True)

    bom_line_ids = fields.One2many("zyra.techpack.bom.line", "techpack_id", string="Materials", copy=True)
    measurement_ids = fields.One2many("zyra.techpack.measurement", "techpack_id", string="Measurement Spec",
                                      copy=True)
    construction_ids = fields.One2many("zyra.techpack.construction", "techpack_id", string="Construction",
                                       copy=True)
    operation_ids = fields.One2many("zyra.techpack.operation", "techpack_id", string="Operation Bulletin",
                                    copy=True)
    artwork_note = fields.Html(string="Artwork")
    label_note = fields.Html(string="Labels")
    packing_note = fields.Html(string="Packing")
    attachment_ids = fields.Many2many("ir.attachment", "zyra_techpack_attachment_rel", "techpack_id",
                                      "attachment_id", string="Documents")

    sam = fields.Float(string="SAM", digits=(16, 2), compute="_compute_sam", store=True)
    material_cost = fields.Monetary(string="Material / pc", compute="_compute_material_cost", store=True,
                                    currency_field="currency_id",
                                    help="Material cost per piece, with wastage, of the dearest colourway.")
    graded_chart_html = fields.Html(string="Graded Chart", compute="_compute_graded_chart_html",
                                    sanitize=False)

    bom_id = fields.Many2one("mrp.bom", string="Odoo Bill of Materials", copy=False, readonly=True,
                             check_company=True)
    sale_line_ids = fields.One2many("sale.order.line", "techpack_id", string="Sale Order Lines")
    production_ids = fields.One2many("mrp.production", "techpack_id", string="Manufacturing Orders")
    sale_order_count = fields.Integer(compute="_compute_link_counts", string="Sale Orders")
    production_count = fields.Integer(compute="_compute_link_counts", string="Manufacturing")

    submitted_date = fields.Datetime(copy=False, readonly=True)
    approved_date = fields.Datetime(copy=False, readonly=True)
    approved_user_id = fields.Many2one("res.users", string="Approved By", copy=False, readonly=True)

    company_id = fields.Many2one(related="style_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")

    _sql_constraints = [
        ("style_revision_unique", "unique(style_id, revision)", "A style cannot have two tech packs with the "
                                                                "same revision number."),
    ]

    # ------------------------------------------------------------------ computes
    @api.depends("style_id.code", "revision")
    def _compute_name(self):
        for techpack in self:
            techpack.name = f"{techpack.style_id.code or ''} · v{techpack.revision}"

    @api.depends("operation_ids.sam")
    def _compute_sam(self):
        for techpack in self:
            techpack.sam = sum(techpack.operation_ids.mapped("sam"))

    @api.depends("bom_line_ids.cost_per_piece", "bom_line_ids.colour_id", "style_id.colour_ids")
    def _compute_material_cost(self):
        for techpack in self:
            by_colour = techpack._material_cost_by_colour()
            techpack.material_cost = max(by_colour.values()) if by_colour else 0.0

    @api.depends("measurement_ids.base_value", "measurement_ids.grade_rule", "measurement_ids.tol_plus",
                 "measurement_ids.tol_minus", "measurement_ids.pom_id", "base_size_id", "measure_unit",
                 "style_id.size_range_id")
    def _compute_graded_chart_html(self):
        for techpack in self:
            techpack.graded_chart_html = techpack._render_graded_chart()

    def _compute_link_counts(self):
        for techpack in self:
            techpack.sale_order_count = len(techpack.sale_line_ids.order_id)
            techpack.production_count = len(techpack.production_ids)

    # ------------------------------------------------------------------ create / write
    @api.model_create_multi
    def create(self, vals_list):
        next_by_style = {}
        for vals in vals_list:
            style_id = vals.get("style_id")
            if style_id and not vals.get("revision"):
                if style_id not in next_by_style:
                    last = self.search([("style_id", "=", style_id)], order="revision desc", limit=1)
                    next_by_style[style_id] = last.revision + 1
                vals["revision"] = next_by_style[style_id]
                next_by_style[style_id] += 1
        techpacks = super().create(vals_list)
        techpacks._check_one_open_revision()
        for techpack in techpacks:
            if not techpack.base_size_id and techpack.style_id.size_range_id.size_ids:
                sizes = techpack.style_id.size_range_id.size_ids.sorted(lambda s: (s.sequence, s.id))
                techpack.base_size_id = sizes[len(sizes) // 2]
        return techpacks

    def write(self, vals):
        if not self.env.context.get("techpack_unlock") and self._LOCKED_FIELDS & set(vals):
            locked = self.filtered(lambda t: t.state in LOCKED_STATES)
            if locked:
                raise UserError(_(
                    "Tech pack %s is approved and cannot be changed. Make a new version instead.",
                    ", ".join(locked.mapped("name"))))
        res = super().write(vals)
        if "state" in vals or "style_id" in vals:
            self._check_one_open_revision()
        return res

    def unlink(self):
        for techpack in self:
            if techpack.state in LOCKED_STATES:
                raise UserError(_("Tech pack %s has been approved and cannot be deleted.", techpack.name))
        return super().unlink()

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for vals in vals_list:
            vals.pop("revision", None)
        return vals_list

    # ------------------------------------------------------------------ constraints
    def _check_one_open_revision(self):
        for style in self.mapped("style_id"):
            open_revs = style.techpack_ids.filtered(lambda t: t.state in OPEN_STATES)
            if len(open_revs) > 1:
                raise ValidationError(_(
                    "Style %(style)s already has an open tech pack (%(rev)s). Only one revision can be in "
                    "draft or submitted at a time.",
                    style=style.code, rev=", ".join(open_revs.sorted("revision")[:-1].mapped("name"))))

    @api.constrains("base_size_id", "style_id")
    def _check_base_size(self):
        for techpack in self:
            if techpack.base_size_id and techpack.base_size_id.range_id != techpack.style_id.size_range_id:
                raise ValidationError(_(
                    "Base size %(size)s is not in the size range of style %(style)s.",
                    size=techpack.base_size_id.name, style=techpack.style_id.code))

    # ------------------------------------------------------------------ workflow
    def _check_group(self, *groups):
        user = self.env.user
        if self.env.su or any(user.has_group(g) for g in groups):
            return True
        raise AccessError(_("You are not allowed to do this on a tech pack."))

    def action_submit(self):
        """Draft → submitted. Tech pack designers and merchandisers may submit."""
        self._check_group(GROUP_DESIGNER, GROUP_MERCHANDISER, GROUP_MANAGER)
        for techpack in self:
            if techpack.state != "draft":
                raise UserError(_("Only a draft tech pack can be submitted (%s).", techpack.name))
            if not techpack.bom_line_ids:
                raise UserError(_("Tech pack %s has no materials: add the bill of materials before submitting.",
                                  techpack.name))
            if techpack.measurement_ids and not techpack.base_size_id:
                raise UserError(_("Tech pack %s needs a base size for its measurement spec.", techpack.name))
        self.sudo().write({"state": "submitted", "submitted_date": fields.Datetime.now()})
        for techpack in self:
            techpack.message_post(body=_("Submitted for approval."))
        return True

    def action_approve(self):
        """Submitted → approved (Factory Manager). The previous approved revision becomes superseded and the
        Odoo bill of materials is generated."""
        self._check_group(GROUP_MANAGER)
        for techpack in self:
            if techpack.state != "submitted":
                raise UserError(_("Only a submitted tech pack can be approved (%s).", techpack.name))
        for techpack in self:
            previous = techpack.style_id.techpack_ids.filtered(lambda t: t.state == "approved" and t != techpack)
            previous.sudo().write({"state": "superseded"})
            techpack.sudo().write({
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "approved_user_id": self.env.user.id,
            })
            techpack.sudo()._generate_bom()
            for old in previous:
                old.message_post(body=_("Superseded by %s.", techpack.name))
            techpack.message_post(body=_("Approved for production."))
        return True

    def action_reset_draft(self):
        """Submitted → draft (send back for changes)."""
        self._check_group(GROUP_DESIGNER, GROUP_MANAGER)
        for techpack in self:
            if techpack.state != "submitted":
                raise UserError(_("Only a submitted tech pack can go back to draft (%s).", techpack.name))
        self.sudo().write({"state": "draft"})
        return True

    def action_new_revision(self):
        """Copy this revision into the next draft revision of the same style."""
        self.ensure_one()
        self._check_group(GROUP_DESIGNER, GROUP_MERCHANDISER, GROUP_MANAGER)
        open_rev = self.style_id.techpack_ids.filtered(lambda t: t.state in OPEN_STATES)
        if open_rev:
            raise UserError(_("Style %(style)s already has an open revision (%(rev)s): finish it first.",
                              style=self.style_id.code, rev=open_rev[0].name))
        new = self.sudo().copy({"style_id": self.style_id.id, "change_note": False})
        new.message_post(body=_("Created from %s.", self.name))
        return new._get_form_action()

    def _copy_to_style(self, style):
        """Copy this revision as draft v1 of another style (lines whose colour/size do not fit are dropped)."""
        self.ensure_one()
        new = self.sudo().copy({
            "style_id": style.id,
            "change_note": _("Copied from %s.", self.name),
            "base_size_id": self.base_size_id.id if self.base_size_id.range_id == style.size_range_id else False,
        })
        new.bom_line_ids.filtered(
            lambda ln: (ln.colour_id and ln.colour_id not in style.colour_ids)
            or (ln.size_id and ln.size_id.range_id != style.size_range_id)).unlink()
        return new

    def _get_form_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "zyra.techpack",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print(self):
        return self.env.ref("zyra_techpack.action_report_techpack").report_action(self)

    def action_view_sale_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_orders")
        action["domain"] = [("id", "in", self.sale_line_ids.order_id.ids)]
        return action

    def action_view_productions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("mrp.mrp_production_action")
        action["domain"] = [("techpack_id", "=", self.id)]
        return action

    def action_view_bom(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.bom",
            "res_id": self.bom_id.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------ BOM generation
    def _generate_bom(self):
        """Create the Odoo BoM of this revision on the style's product. Lines for one colourway / size apply only
        to those variants; quantity per piece includes wastage. Earlier BoMs of the style are archived."""
        self.ensure_one()
        style = self.style_id
        template = style._ensure_product()
        ptavs = template.attribute_line_ids.product_template_value_ids
        colour_ptav = {p.product_attribute_value_id.garment_colour_id.id: p for p in ptavs
                       if p.product_attribute_value_id.garment_colour_id}
        size_ptav = {p.product_attribute_value_id.garment_size_id.id: p for p in ptavs
                     if p.product_attribute_value_id.garment_size_id}
        line_cmds = []
        for line in self.bom_line_ids:
            restrict = self.env["product.template.attribute.value"]
            if line.colour_id:
                restrict |= colour_ptav.get(line.colour_id.id, restrict)
            if line.size_id:
                restrict |= size_ptav.get(line.size_id.id, restrict)
            line_cmds.append(Command.create({
                "product_id": line.product_id.id,
                "product_qty": line.qty_with_wastage,
                "product_uom_id": line.uom_id.id,
                "bom_product_template_attribute_value_ids": [Command.set(restrict.ids)],
            }))
        old_boms = self.env["mrp.bom"].search([("product_tmpl_id", "=", template.id),
                                               ("techpack_id", "!=", self.id)])
        if self.bom_id:
            self.bom_id.write({"bom_line_ids": [Command.clear()] + line_cmds})
            bom = self.bom_id
        else:
            bom = self.env["mrp.bom"].create({
                "product_tmpl_id": template.id,
                "product_qty": 1.0,
                "type": "normal",
                "code": self.name,
                "techpack_id": self.id,
                "company_id": self.company_id.id,
                "sequence": 1,
                "bom_line_ids": line_cmds,
            })
            self.with_context(techpack_unlock=True).bom_id = bom
        old_boms.write({"active": False})
        return bom

    # ------------------------------------------------------------------ figures
    def _material_cost_by_colour(self):
        """{colour_id: material cost per piece with wastage} for each colourway (lines for all colourways count
        in each). Size-specific lines count at their own cost (no size mix known here)."""
        self.ensure_one()
        result = {}
        colours = self.style_id.colour_ids or self.bom_line_ids.colour_id
        for colour in colours:
            lines = self.bom_line_ids.filtered(lambda ln, c=colour: not ln.colour_id or ln.colour_id == c)
            result[colour.id] = sum(lines.mapped("cost_per_piece"))
        if not colours and self.bom_line_ids:
            result[False] = sum(self.bom_line_ids.mapped("cost_per_piece"))
        return result

    def material_requirements(self, qty_by_variant):
        """Material needed for an order.

        :param qty_by_variant: ``{(colour_id, size_id): qty}`` (ids or records)
        :return: list of dicts ``{product_id, colour_id, uom_id, qty_net, qty_with_wastage}`` (ids), one per
            material and colourway; plus ``material_kind`` and ``price_unit`` for convenience.
            Fabric required = Σ(order qty per cell × consumption) × (1 + wastage %).
        """
        self.ensure_one()
        totals = defaultdict(lambda: [0.0, 0.0])
        meta = {}
        for (colour, size), qty in qty_by_variant.items():
            colour_id = colour.id if hasattr(colour, "id") else (colour or False)
            size_id = size.id if hasattr(size, "id") else (size or False)
            if not qty:
                continue
            for line in self.bom_line_ids:
                if line.colour_id and line.colour_id.id != colour_id:
                    continue
                if line.size_id and line.size_id.id != size_id:
                    continue
                key = (line.product_id.id, colour_id, line.uom_id.id)
                net = qty * line.consumption
                totals[key][0] += net
                totals[key][1] += net * (1.0 + line.wastage_pct / 100.0)
                meta.setdefault(key, (line.material_kind, line.price_unit))
        result = []
        for key, (net, gross) in totals.items():
            product_id, colour_id, uom_id = key
            result.append({
                "product_id": product_id,
                "colour_id": colour_id,
                "uom_id": uom_id,
                "qty_net": net,
                "qty_with_wastage": gross,
                "material_kind": meta[key][0],
                "price_unit": meta[key][1],
            })
        return result

    def _get_sizes(self):
        self.ensure_one()
        return self.style_id.size_range_id.size_ids.sorted(lambda s: (s.sequence, s.id))

    def get_graded_chart(self):
        """Graded measurement = base value + (size steps from base size × grade rule).

        :return: ``{pom_id: {size_id: value}}``
        """
        self.ensure_one()
        sizes = self._get_sizes()
        if not sizes:
            return {}
        base = self.base_size_id if self.base_size_id in sizes else sizes[0]
        base_index = list(sizes).index(base)
        chart = {}
        for line in self.measurement_ids:
            chart[line.pom_id.id] = {
                size.id: round(line.base_value + (index - base_index) * line.grade_rule, 4)
                for index, size in enumerate(sizes)
            }
        return chart

    def _render_graded_chart(self):
        self.ensure_one()
        sizes = self._get_sizes()
        if not sizes or not self.measurement_ids:
            return False
        chart = self.get_graded_chart()
        head = "".join(
            f'<th class="text-end{" o_zyra_base_size" if size == self.base_size_id else ""}">'
            f'{escape(size.name)}{" *" if size == self.base_size_id else ""}</th>' for size in sizes)
        rows = []
        for line in self.measurement_ids:
            cells = "".join(
                f'<td class="text-end{" o_zyra_base_size" if size == self.base_size_id else ""}">'
                f'{chart[line.pom_id.id][size.id]:.2f}</td>' for size in sizes)
            rows.append(
                f"<tr><td>{escape(line.pom_id.code or '')} · {escape(line.pom_id.name or '')}</td>"
                f'<td class="text-nowrap">+{line.tol_plus:.2f} / −{line.tol_minus:.2f}</td>{cells}</tr>')
        unit = dict(self._fields["measure_unit"].selection).get(self.measure_unit, "")
        caption = _("Measured in %(unit)s · base size %(size)s highlighted",
                    unit=unit.lower(), size=self.base_size_id.name or "")
        return Markup(
            f'<div class="o_zyra_graded_chart"><div class="text-muted small mb-2">{escape(caption)}</div>'
            f'<table class="table table-sm"><thead><tr><th>{escape(_("Point of Measure"))}</th>'
            f'<th>{escape(_("Tolerance"))}</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
