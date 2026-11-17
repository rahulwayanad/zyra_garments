from collections import OrderedDict, defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PACK_KINDS = [
    ("solid", "Solid colour, solid size"),
    ("assorted", "Solid colour, assorted sizes"),
    ("ratio", "Ratio pack"),
]


class GarmentPackPlan(models.Model):
    """How one production order is packed: pack kind, carton, pieces per carton, cartons planned."""

    _name = "garment.pack.plan"
    _description = "Pack Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _check_company_auto = True

    name = fields.Char(string="Plan", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    order_id = fields.Many2one(
        "garment.order", string="Order", required=True, index=True, tracking=True, check_company=True,
        domain="[('state', 'in', ('confirmed', 'in_production', 'packed', 'shipped'))]")
    style_id = fields.Many2one(related="order_id.style_id", string="Style")
    buyer_id = fields.Many2one(related="order_id.buyer_id", string="Buyer", store=True)
    state = fields.Selection(
        [("draft", "Draft"), ("packing", "Packing"), ("packed", "Packed"), ("shipped", "Shipped")],
        compute="_compute_state", store=True, tracking=True, index=True,
        help="Follows the cartons: packing once one carton is packed, packed when every planned carton is "
             "packed, shipped when every carton has shipped.")

    # How it is packed
    pack_kind = fields.Selection(PACK_KINDS, string="Pack Kind", required=True, default="assorted", tracking=True)
    ratio_line_ids = fields.One2many("garment.pack.plan.ratio", "plan_id", string="Ratio", copy=True)
    ratio_name = fields.Char(string="Ratio Pack", compute="_compute_ratio_name")
    pieces_per_carton = fields.Integer(
        string="Pieces per Carton", compute="_compute_pieces_per_carton", store=True, readonly=False,
        help="Entered for solid packs; the sum of the ratio for assorted and ratio packs.")
    first_carton_no = fields.Integer(string="First Carton No.", default=1)

    # Carton
    carton_product_id = fields.Many2one("product.product", string="Carton", check_company=True)
    length_cm = fields.Float(string="Length (cm)", digits=(16, 2), default=60.0)
    width_cm = fields.Float(string="Width (cm)", digits=(16, 2), default=40.0)
    height_cm = fields.Float(string="Height (cm)", digits=(16, 2), default=30.0)
    carton_cbm = fields.Float(string="CBM per Carton", digits=(16, 3), compute="_compute_carton_cbm", store=True)
    net_weight_per_piece = fields.Float(string="Net Weight per Piece (kg)", digits=(16, 3))
    empty_carton_weight = fields.Float(string="Empty Carton Weight (kg)", digits=(16, 3))

    # Totals
    carton_ids = fields.One2many("garment.carton", "plan_id", string="Carton List")
    pieces_planned = fields.Integer(related="order_id.qty_ordered", string="Pieces Planned")
    order_qty_packed = fields.Integer(related="order_id.qty_packed", string="Order Packed")
    cartons_planned = fields.Integer(string="Cartons Planned", compute="_compute_cartons_planned", store=True)
    carton_count = fields.Integer(string="Cartons", compute="_compute_carton_figures", store=True)
    cartons_packed = fields.Integer(string="Packed", compute="_compute_carton_figures", store=True,
                                    help="Cartons packed, shipped ones included.")
    cartons_shipped = fields.Integer(string="Cartons Shipped", compute="_compute_carton_figures", store=True)
    pieces_packed = fields.Integer(string="Pieces in Packed Cartons", compute="_compute_carton_figures", store=True)
    pieces_waiting_stock = fields.Integer(string="Waiting for Stock", compute="_compute_carton_figures",
                                          store=True, help="Pieces in packed cartons not yet posted to stock.")
    cartons_packed_pct = fields.Float(string="Cartons Packed %", compute="_compute_carton_figures", store=True)
    net_weight = fields.Float(string="Net Weight (kg)", digits=(16, 2), compute="_compute_weights", store=True)
    gross_weight = fields.Float(string="Gross kg", digits=(16, 1), compute="_compute_weights", store=True)
    volume_cbm = fields.Float(string="CBM", digits=(16, 2), compute="_compute_weights", store=True)
    production_ids = fields.Many2many("mrp.production", string="Finished Goods Orders", copy=False)
    production_count = fields.Integer(compute="_compute_production_count")

    _sql_constraints = [
        ("first_carton_positive", "CHECK(first_carton_no >= 1)", "The first carton number starts at 1 or more."),
    ]

    # ------------------------------------------------------------------ computes
    @api.depends("ratio_line_ids.qty", "ratio_line_ids.size_id", "ratio_line_ids.colour_id")
    def _compute_ratio_name(self):
        for plan in self:
            lines = plan.ratio_line_ids.sorted(lambda r: (r.colour_id.name or "", r.size_id.sequence, r.size_id.id))
            if not lines:
                plan.ratio_name = False
                continue
            sizes = lines.mapped("size_id").sorted(lambda s: (s.sequence, s.id))
            span = sizes[0].name if len(sizes) == 1 else "%s–%s" % (sizes[0].name, sizes[-1].name)
            plan.ratio_name = _("Prepack %(ratio)s (%(span)s)", ratio="-".join(str(q) for q in lines.mapped("qty")),
                                span=span)

    @api.depends("pack_kind", "ratio_line_ids.qty")
    def _compute_pieces_per_carton(self):
        for plan in self:
            if plan.pack_kind != "solid":
                plan.pieces_per_carton = sum(plan.ratio_line_ids.mapped("qty"))
            elif not plan.pieces_per_carton:
                plan.pieces_per_carton = 0

    @api.depends("length_cm", "width_cm", "height_cm")
    def _compute_carton_cbm(self):
        for plan in self:
            plan.carton_cbm = round(plan.length_cm * plan.width_cm * plan.height_cm / 1e6, 3)

    @api.depends("pack_kind", "pieces_per_carton", "ratio_line_ids.qty", "ratio_line_ids.size_id",
                 "ratio_line_ids.colour_id", "order_id.line_ids.qty_ordered")
    def _compute_cartons_planned(self):
        for plan in self:
            plan.cartons_planned = len(plan._plan_carton_contents())

    @api.depends("carton_ids.state", "carton_ids.pieces", "carton_ids.stock_posted", "cartons_planned")
    def _compute_carton_figures(self):
        for plan in self:
            cartons = plan.carton_ids
            packed = cartons.filtered(lambda c: c.state in ("packed", "shipped"))
            plan.carton_count = len(cartons)
            plan.cartons_packed = len(packed)
            plan.cartons_shipped = len(cartons.filtered(lambda c: c.state == "shipped"))
            plan.pieces_packed = sum(packed.mapped("pieces"))
            plan.pieces_waiting_stock = sum(packed.filtered(lambda c: not c.stock_posted).mapped("pieces"))
            planned = max(plan.cartons_planned, len(cartons))
            plan.cartons_packed_pct = 100.0 * len(packed) / planned if planned else 0.0

    @api.depends("order_id.qty_ordered", "net_weight_per_piece", "empty_carton_weight", "cartons_planned",
                 "carton_cbm")
    def _compute_weights(self):
        for plan in self:
            plan.net_weight = plan.order_id.qty_ordered * plan.net_weight_per_piece
            plan.gross_weight = plan.net_weight + plan.cartons_planned * plan.empty_carton_weight
            plan.volume_cbm = plan.cartons_planned * plan.carton_cbm

    @api.depends("carton_ids.state", "cartons_planned")
    def _compute_state(self):
        for plan in self:
            cartons = plan.carton_ids
            done = cartons.filtered(lambda c: c.state in ("packed", "shipped"))
            if not done:
                plan.state = "draft"
            elif cartons and all(c.state == "shipped" for c in cartons) and len(cartons) >= plan.cartons_planned:
                plan.state = "shipped"
            elif len(done) == len(cartons) and len(cartons) >= plan.cartons_planned:
                plan.state = "packed"
            else:
                plan.state = "packing"

    def _compute_production_count(self):
        for plan in self:
            plan.production_count = len(plan.production_ids)

    # ------------------------------------------------------------------ constraints
    @api.constrains("pack_kind", "ratio_line_ids")
    def _check_ratio(self):
        for plan in self:
            for line in plan.ratio_line_ids:
                if line.size_id not in plan.order_id.size_ids:
                    raise ValidationError(_("Size %s is not in the grid of the order.", line.size_id.name))
                if plan.pack_kind == "ratio" and not line.colour_id:
                    raise ValidationError(_("A ratio pack names the colourway of every ratio line."))
                if plan.pack_kind != "ratio" and line.colour_id:
                    raise ValidationError(_("Only a ratio pack mixes colourways; leave the colour empty."))

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.pack.plan") or _("New")
            if vals.get("pack_kind", "assorted") != "solid":
                vals.pop("pieces_per_carton", None)  # the sum of the ratio
        return super().create(vals_list)

    def unlink(self):
        if self.carton_ids.filtered(lambda c: c.state != "planned"):
            raise UserError(_("A pack plan with packed cartons cannot be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------ carton maths
    def _plan_carton_contents(self):
        """Carton contents for the whole order: a list of {(colour_id, size_id): qty}, one dict per carton.

        - solid: one colour and size per carton, ``pieces_per_carton`` each, the last carton of a cell short;
        - assorted: one colour per carton, sizes by the ratio, until every ratio size of the colour is packed;
        - ratio: colours and sizes by the ratio, until every ratio cell of the order is packed.
        """
        self.ensure_one()
        order = self.order_id
        remaining = OrderedDict()
        for line in order.line_ids.sorted(lambda l: (l.colour_id.name or "", l.size_id.sequence, l.size_id.id)):
            if line.qty_ordered > 0:
                remaining[(line.colour_id.id, line.size_id.id)] = line.qty_ordered
        cartons = []
        if self.pack_kind == "solid":
            ppc = self.pieces_per_carton
            if ppc <= 0:
                return []
            for cell, qty in remaining.items():
                while qty > 0:
                    take = min(ppc, qty)
                    cartons.append({cell: take})
                    qty -= take
            return cartons
        ratio = [(r.colour_id.id, r.size_id.id, r.qty) for r in self.ratio_line_ids if r.qty > 0]
        if not ratio:
            return []
        if self.pack_kind == "assorted":
            colours = list(OrderedDict.fromkeys(c for c, _s in remaining))
            groups = [[((colour, size), qty) for _c, size, qty in ratio] for colour in colours]
        else:
            groups = [[((colour, size), qty) for colour, size, qty in ratio]]
        for group in groups:
            while any(remaining.get(cell, 0) > 0 for cell, _q in group):
                content = {}
                for cell, qty in group:
                    take = min(qty, remaining.get(cell, 0))
                    if take > 0:
                        content[cell] = take
                        remaining[cell] -= take
                cartons.append(content)
        return cartons

    # ------------------------------------------------------------------ buttons
    def action_generate_cartons(self):
        """Create the planned cartons not created yet ("Generate More Cartons")."""
        Carton = self.env["garment.carton"]
        for plan in self:
            if plan.pieces_per_carton <= 0:
                raise UserError(_("Set the pieces per carton (or the ratio) before generating cartons."))
            contents = plan._plan_carton_contents()
            existing = len(plan.carton_ids)
            vals_list = []
            for index, content in enumerate(contents[existing:], start=existing):
                vals_list.append({
                    "plan_id": plan.id,
                    "number": plan.first_carton_no + index,
                    "line_ids": [fields.Command.create({"colour_id": c, "size_id": s, "qty": q})
                                 for (c, s), q in content.items()],
                })
            if vals_list:
                Carton.create(vals_list)
                plan.message_post(body=_("%s cartons generated.", len(vals_list)))
        return True

    def action_assign_sscc(self):
        self.carton_ids.filtered(lambda c: not c.sscc)._assign_sscc()
        return True

    def action_open_pack_wizard(self):
        self.ensure_one()
        if not self.carton_ids:
            self.action_generate_cartons()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pack / Scan Cartons"),
            "res_model": "garment.carton.pack.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_plan_id": self.id},
        }

    def action_view_cartons(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_shipping.action_garment_carton")
        action["domain"] = [("plan_id", "=", self.id)]
        action["context"] = {"default_plan_id": self.id}
        return action

    def action_view_productions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Finished Goods Orders"),
            "res_model": "mrp.production",
            "view_mode": "list,form",
            "domain": [("id", "in", self.production_ids.ids)],
        }

    def action_print_packing_list(self):
        return self.env.ref("zyra_garment_shipping.action_report_pack_plan_packing_list").report_action(self)


    def _garment_post_cells(self, cartons, stage, sign, ref):
        """Post the pieces of ``cartons`` to the order through the merch progress API."""
        self.ensure_one()
        totals = defaultdict(int)
        for line in cartons.line_ids:
            totals[(line.colour_id.id, line.size_id.id)] += line.qty
        for (colour_id, size_id), qty in totals.items():
            if qty:
                self.order_id._garment_add_progress(stage, colour_id, size_id, sign * qty, ref=ref)

    # ------------------------------------------------------------------ finished goods
    def _garment_variant(self, colour, size):
        """Product variant of a grid cell: the variant on the grid line, else the style's variant."""
        self.ensure_one()
        line = self.order_id.line_ids.filtered(lambda l: l.colour_id == colour and l.size_id == size)[:1]
        if line.product_id:
            return line.product_id
        style = self.order_id.style_id
        if style.product_tmpl_id and hasattr(style, "_get_variant"):
            return style._get_variant(colour, size) or self.env["product.product"]
        return self.env["product.product"]

    def action_post_to_stock(self):
        """Post packed garments to stock: one manufacturing order per variant for exactly the packed quantity
        (architecture rule), consuming the components reserved in stock."""
        for plan in self:
            cartons = plan.carton_ids.filtered(lambda c: c.state in ("packed", "shipped") and not c.stock_posted)
            if not cartons:
                raise UserError(_("No packed cartons are waiting for stock."))
            qty_by_variant = defaultdict(int)
            missing = set()
            for line in cartons.line_ids:
                variant = plan._garment_variant(line.colour_id, line.size_id)
                if variant:
                    qty_by_variant[variant] += line.qty
                else:
                    missing.add(line.colour_id.name + " / " + line.size_id.name)
            if missing:
                raise UserError(_("The style has no product variant for %s. Generate the variants first.",
                                  ", ".join(sorted(missing))))
            productions = self.env["mrp.production"]
            for variant, qty in qty_by_variant.items():
                productions |= plan._garment_produce(variant, qty)
            cartons.write({"stock_posted": True})
            plan.production_ids = [fields.Command.link(p.id) for p in productions]
            plan.message_post(body=_("Posted %(pieces)s pieces of %(cartons)s cartons to stock: %(mos)s.",
                                     pieces=sum(qty_by_variant.values()), cartons=len(cartons),
                                     mos=", ".join(productions.mapped("name"))))
        return True

    def _garment_produce(self, variant, qty):
        self.ensure_one()
        Production = self.env["mrp.production"]
        bom = self.env["mrp.bom"]._bom_find(variant, company_id=self.company_id.id).get(variant)
        mo = Production.create({
            "product_id": variant.id,
            "product_qty": qty,
            "product_uom_id": variant.uom_id.id,
            "bom_id": bom.id if bom else False,
            "company_id": self.company_id.id,
            "origin": "%s %s" % (self.name, self.order_id.name),
        })
        mo.action_confirm()
        mo.action_assign()
        mo.qty_producing = qty
        mo._set_qty_producing()
        for move in mo.move_raw_ids:
            if move.product_id.tracking != "none":
                # Only what is reserved (with its lot) is consumed; fabric issue is booked by materials.
                move.move_line_ids.filtered(lambda ml: not ml.lot_id).unlink()
            move.picked = True
        # Finished moves stay unpicked: mrp counts picked finished quantity as already produced and
        # would then post nothing (the finished move gets cancelled).
        result = mo.with_context(skip_consumption=True, skip_backorder=True).button_mark_done()
        if mo.state != "done":
            raise UserError(_("Manufacturing order %(mo)s could not be closed (%(res)s).", mo=mo.name, res=result))
        return mo


class GarmentPackPlanRatio(models.Model):
    _name = "garment.pack.plan.ratio"
    _description = "Pack Plan Ratio Line"
    _order = "plan_id, colour_id, size_sequence, id"

    plan_id = fields.Many2one("garment.pack.plan", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True)
    colour_id = fields.Many2one("garment.colour", string="Colourway",
                                help="Ratio packs only: the colourway of this part of the carton.")
    size_id = fields.Many2one("garment.size", string="Size", required=True)
    size_sequence = fields.Integer(related="size_id.sequence", store=True)
    qty = fields.Integer(string="Pieces", required=True, default=1)

    _sql_constraints = [
        ("qty_positive", "CHECK(qty > 0)", "A ratio line packs at least one piece."),
    ]
