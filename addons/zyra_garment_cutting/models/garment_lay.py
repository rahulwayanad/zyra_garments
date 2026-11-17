from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare, float_round

LAY_STATES = [
    ("planned", "Planned"),
    ("spread", "Spread"),
    ("cut", "Cut"),
    ("bundled", "Bundled"),
    ("cancel", "Cancelled"),
]


class GarmentLay(models.Model):
    """A lay: plies of fabric spread on a cutting table under one marker, then cut and bundled.

    Fabric laid = plies × (lay length + end allowance per ply). Pieces = plies × Σ marker ratio.
    Cutting a lay consumes the fabric of its rolls and posts 'cut' progress on the production order."""

    _name = "garment.lay"
    _description = "Lay"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "order_id, lay_no, id"
    _check_company_auto = True

    name = fields.Char(string="Lay", readonly=True, copy=False, index=True)
    lay_no = fields.Integer(readonly=True, copy=False)
    state = fields.Selection(LAY_STATES, default="planned", required=True, tracking=True, copy=False)
    plan_id = fields.Many2one("garment.cut.plan", string="Cut Plan", required=True, ondelete="cascade",
                              index=True, check_company=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    order_id = fields.Many2one(related="plan_id.order_id", store=True, index=True, string="Order")
    colour_id = fields.Many2one(related="plan_id.colour_id", store=True, string="Colourway")
    style_id = fields.Many2one(related="plan_id.style_id", store=True)
    fabric_id = fields.Many2one(related="plan_id.fabric_id", store=True, string="Fabric")
    marker_id = fields.Many2one("garment.marker", required=True, ondelete="restrict", tracking=True)
    ratio_text = fields.Char(related="marker_id.ratio_text", string="Size Ratio Detail")
    ratio_short = fields.Char(related="marker_id.ratio_short", string="Size Ratio")
    marker_efficiency = fields.Float(related="marker_id.efficiency_pct", string="Marker Efficiency %")
    pieces_per_ply = fields.Integer(related="marker_id.pieces_per_ply")

    plies_planned = fields.Integer(string="Planned Plies", required=True, default=1)
    plies_actual = fields.Integer(string="Actual Plies", compute="_compute_figures", store=True)
    pieces_planned = fields.Integer(string="Planned Pieces", compute="_compute_figures", store=True)
    pieces = fields.Integer(string="Pieces in Lay", compute="_compute_figures", store=True)
    lay_length = fields.Float(string="Lay Length (m)", digits=(16, 3), required=True)
    end_allowance_m = fields.Float(string="End Allowance (m)", digits=(16, 3))
    fabric_laid = fields.Float(string="Fabric Laid (m)", compute="_compute_figures", store=True, digits=(16, 2))
    end_loss_pct = fields.Float(string="End Loss %", compute="_compute_figures", store=True, digits=(16, 1))
    end_bits_m = fields.Float(string="End Bits Returned (m)", digits=(16, 2), tracking=True)

    roll_line_ids = fields.One2many("garment.lay.roll", "lay_id", string="Rolls")
    shades = fields.Char(string="Shade", compute="_compute_shades", store=True)
    mixed_shades = fields.Boolean(compute="_compute_shades", store=True)

    lay_date = fields.Date(string="Lay Date", default=fields.Date.context_today)
    cut_date = fields.Date(string="Cut On", readonly=True, copy=False)
    table_name = fields.Char(string="Cutting Table")
    spreader_id = fields.Many2one("hr.employee", string="Spreader")
    cutter_id = fields.Many2one("hr.employee", string="Cutter")
    bundle_size = fields.Integer(string="Pieces per Bundle", default=40)

    bundle_ids = fields.One2many("garment.bundle", "lay_id", string="Bundles")
    bundle_count = fields.Integer(compute="_compute_bundle_count", string="Bundles")
    move_ids = fields.One2many("stock.move", "garment_lay_id", string="Fabric Moves")
    proposal_id = fields.Many2one("garment.cut.plan.proposal", compute="_compute_proposal")

    _sql_constraints = [
        ("plies_planned_positive", "CHECK(plies_planned > 0)", "A lay needs at least one planned ply."),
        ("lay_length_positive", "CHECK(lay_length > 0)", "Lay length must be above zero."),
        ("end_allowance_positive", "CHECK(end_allowance_m >= 0)", "End allowance cannot be negative."),
    ]

    # ------------------------------------------------------------------
    @api.depends("plies_planned", "roll_line_ids.plies", "marker_id.pieces_per_ply", "lay_length",
                 "end_allowance_m")
    def _compute_figures(self):
        for lay in self:
            lay.plies_actual = sum(lay.roll_line_ids.mapped("plies"))
            ppp = lay.marker_id.pieces_per_ply
            lay.pieces_planned = lay.plies_planned * ppp
            lay.pieces = lay.plies_actual * ppp
            plies = lay.plies_actual or lay.plies_planned
            lay.fabric_laid = plies * (lay.lay_length + lay.end_allowance_m)
            lay.end_loss_pct = lay.fabric_laid and 100.0 * plies * lay.end_allowance_m / lay.fabric_laid or 0.0

    @api.depends("roll_line_ids.lot_id.shade_group")
    def _compute_shades(self):
        for lay in self:
            shades = sorted({s for s in lay.roll_line_ids.mapped("lot_id.shade_group") if s})
            lay.shades = ", ".join(shades)
            lay.mixed_shades = len(shades) > 1

    def _compute_bundle_count(self):
        for lay in self:
            lay.bundle_count = len(lay.bundle_ids)

    def _compute_proposal(self):
        for lay in self:
            lay.proposal_id = self.env["garment.cut.plan.proposal"].search([("lay_id", "=", lay.id)], limit=1)

    @api.depends("name", "order_id.name", "style_id.code")
    def _compute_display_name(self):
        for lay in self:
            lay.display_name = lay.name or _("New lay")

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        lays = super().create(vals_list)
        for lay in lays:
            last = self.search([("order_id", "=", lay.order_id.id), ("id", "!=", lay.id)],
                               order="lay_no desc", limit=1).lay_no
            lay.lay_no = (last or 0) + 1
            tail = (lay.order_id.name or "").rsplit("/", 1)[-1]
            lay.name = "%s-C%02d" % (tail, lay.lay_no)
        return lays

    def write(self, vals):
        locked = {"marker_id", "plies_planned", "lay_length", "end_allowance_m"}
        if set(vals) & locked and self.filtered(lambda l: l.state in ("cut", "bundled")):
            raise UserError(_("A cut lay cannot change its marker, plies or length."))
        res = super().write(vals)
        if "state" in vals:
            self.plan_id._update_state_from_lays()
        return res

    def unlink(self):
        if self.filtered(lambda l: l.state in ("cut", "bundled")):
            raise UserError(_("A cut lay cannot be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_spread(self):
        for lay in self:
            if lay.state != "planned":
                raise UserError(_("Only a planned lay can be spread."))
            lay.state = "spread"
        return True

    def _check_rolls(self):
        """Rule: only approved fabric rolls of the plan's fabric may be laid, each with enough metres."""
        self.ensure_one()
        if not self.roll_line_ids or not self.plies_actual:
            raise UserError(_("Record the rolls and plies spread on lay %s before cutting.", self.name))
        needed = {}
        for line in self.roll_line_ids:
            lot = line.lot_id
            if not lot.is_fabric_roll or lot.roll_status != "approved":
                raise UserError(_("Roll %(roll)s is not approved (%(status)s); only approved rolls may be laid.",
                                  roll=lot.name, status=lot.roll_status or _("not a fabric roll")))
            if self.fabric_id and lot.product_id != self.fabric_id:
                raise UserError(_("Roll %(roll)s is %(product)s, not the plan's fabric %(fabric)s.",
                                  roll=lot.name, product=lot.product_id.display_name,
                                  fabric=self.fabric_id.display_name))
            needed[lot] = needed.get(lot, 0.0) + line.fabric_used
        for lot, qty in needed.items():
            available = lot._garment_roll_available()
            if float_compare(qty, available, precision_digits=2) > 0:
                raise UserError(_("Roll %(roll)s has %(available).2f m in stock; lay %(lay)s needs %(qty).2f m.",
                                  roll=lot.name, available=available, lay=self.name, qty=qty))

    def action_cut(self):
        """Confirm the cut: consume the fabric of the rolls and post 'cut' progress per size."""
        for lay in self:
            if lay.state not in ("planned", "spread"):
                raise UserError(_("Lay %s is already cut.", lay.name))
            if lay.plan_id.state not in ("approved", "cutting"):
                raise UserError(_("Approve cut plan %s before cutting its lays.", lay.plan_id.name))
            lay._check_rolls()
            lay._consume_fabric()
            for size_id, ratio in lay.marker_id._ratio_by_size().items():
                lay.order_id._garment_add_progress("cut", lay.colour_id.id, size_id, lay.plies_actual * ratio,
                                                   ref=lay.name)
            lay.write({"state": "cut", "cut_date": fields.Date.context_today(lay)})
            lay.message_post(body=_("Cut %(pieces)s pieces from %(plies)s plies (%(fabric).2f m laid).",
                                    pieces=lay.pieces, plies=lay.plies_actual, fabric=lay.fabric_laid))
        return True

    def _consume_fabric(self):
        """One done stock move per roll from its stock location to the production location."""
        self.ensure_one()
        Move = self.env["stock.move"].sudo()
        meter = self.env.ref("uom.product_uom_meter")
        for line in self.roll_line_ids:
            lot = line.lot_id
            product = lot.product_id
            qty = line.fabric_used
            if product.uom_id.category_id == meter.category_id:
                qty = meter._compute_quantity(qty, product.uom_id)
            qty = float_round(qty, precision_rounding=product.uom_id.rounding)
            if qty <= 0:
                continue
            company = lot.company_id or self.company_id or self.env.company
            source = lot._garment_roll_location()
            dest = product.with_company(company).property_stock_production
            move = Move.create({
                "name": _("Lay %(lay)s · roll %(roll)s", lay=self.name, roll=lot.name),
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": qty,
                "location_id": source.id,
                "location_dest_id": dest.id,
                "company_id": company.id,
                "garment_lay_id": self.id,
                "origin": self.name,
                "move_line_ids": [Command.create({
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "lot_id": lot.id,
                    "quantity": qty,
                    "location_id": source.id,
                    "location_dest_id": dest.id,
                    "company_id": company.id,
                })],
            })
            move._action_confirm()
            move.picked = True
            move._action_done()
        return True

    def action_create_bundles(self):
        """Cut → bundled: one bundle per size, ratio copy and roll segment, split at the bundle size."""
        Bundle = self.env["garment.bundle"]
        for lay in self:
            if lay.state != "cut":
                raise UserError(_("Cut lay %s before bundling it.", lay.name))
            vals_list = lay._bundle_vals()
            Bundle.create(vals_list)
            lay.state = "bundled"
        return True

    def _bundle_vals(self):
        self.ensure_one()
        vals_list = []
        number = 0
        segments = []
        ply = 0
        for line in self.roll_line_ids.sorted(lambda l: (l.sequence, l.id)):
            if line.plies <= 0:
                continue
            segments.append((line, ply + 1, ply + line.plies))
            ply += line.plies
        sizes = self.marker_id.line_ids.sorted(lambda l: (l.size_id.sequence, l.size_id.id))
        for marker_line in sizes:
            for _copy in range(marker_line.ratio):
                for roll_line, first, last in segments:
                    step = self.bundle_size if self.bundle_size > 0 else (last - first + 1)
                    start = first
                    while start <= last:
                        end = min(start + step - 1, last)
                        number += 1
                        vals_list.append({
                            "lay_id": self.id,
                            "bundle_no": number,
                            "size_id": marker_line.size_id.id,
                            "roll_id": roll_line.lot_id.id,
                            "ply_from": start,
                            "ply_to": end,
                        })
                        start = end + 1
        return vals_list

    def action_cancel(self):
        for lay in self:
            if lay.state in ("cut", "bundled"):
                raise UserError(_("Lay %s is cut and cannot be cancelled.", lay.name))
            lay.state = "cancel"
        return True

    def action_reset_planned(self):
        self.filtered(lambda l: l.state in ("spread", "cancel")).write({"state": "planned"})
        return True

    def action_print_tickets(self):
        bundles = self.mapped("bundle_ids")
        if not bundles:
            raise UserError(_("Bundle the lay before printing tickets."))
        return self.env.ref("zyra_garment_cutting.action_report_bundle_ticket").report_action(bundles)

    def action_issue_bundles(self):
        bundles = self.mapped("bundle_ids").filtered(lambda b: b.stage == "cut")
        if not bundles:
            raise UserError(_("No bundle of this lay is waiting to be issued."))
        return bundles.action_open_issue_wizard()

    def action_return_end_bits(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Return End Bits"),
            "res_model": "garment.lay.end.bits",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lay_id": self.id, "default_end_bits_m": self.end_bits_m},
        }

    def action_view_bundles(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_cutting.action_garment_bundle")
        action["domain"] = [("lay_id", "=", self.id)]
        action["context"] = {}
        return action


class GarmentLayRoll(models.Model):
    """A roll spread on a lay, with its plies. Ply numbers run on from roll to roll."""

    _name = "garment.lay.roll"
    _description = "Lay Roll"
    _order = "lay_id, sequence, id"

    lay_id = fields.Many2one("garment.lay", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="lay_id.company_id", store=True)
    sequence = fields.Integer(default=10)
    fabric_id = fields.Many2one(related="lay_id.fabric_id")
    lot_id = fields.Many2one("stock.lot", string="Roll", required=True, ondelete="restrict",
                             domain="[('is_fabric_roll', '=', True), ('roll_status', '=', 'approved'),"
                                    " ('product_id', '=?', fabric_id)]")
    shade = fields.Char(related="lot_id.shade_group", string="Shade")
    dye_lot = fields.Char(related="lot_id.dye_lot")
    plies = fields.Integer(required=True, default=1)
    ply_from = fields.Integer(compute="_compute_ply_range")
    ply_to = fields.Integer(compute="_compute_ply_range")
    fabric_used = fields.Float(string="Fabric (m)", compute="_compute_fabric_used", digits=(16, 2))

    _sql_constraints = [("plies_positive", "CHECK(plies > 0)", "Plies on a roll must be above zero.")]

    @api.depends("plies", "lay_id.lay_length", "lay_id.end_allowance_m")
    def _compute_fabric_used(self):
        for line in self:
            line.fabric_used = line.plies * (line.lay_id.lay_length + line.lay_id.end_allowance_m)

    @api.depends("lay_id.roll_line_ids.plies", "lay_id.roll_line_ids.sequence")
    def _compute_ply_range(self):
        for lay in self.mapped("lay_id"):
            ply = 0
            for line in lay.roll_line_ids.sorted(lambda l: (l.sequence, l.id or 0)):
                line.ply_from = ply + 1
                ply += line.plies
                line.ply_to = ply
        for line in self.filtered(lambda l: not l.lay_id):
            line.ply_from = line.ply_to = 0

    @api.constrains("lot_id")
    def _check_roll_approved(self):
        for line in self:
            if line.lay_id.state in ("cut", "bundled"):
                continue
            if not line.lot_id.is_fabric_roll or line.lot_id.roll_status != "approved":
                raise ValidationError(_("Roll %s is not approved; only approved rolls may be laid.",
                                        line.lot_id.name))

    def write(self, vals):
        if self.filtered(lambda l: l.lay_id.state in ("cut", "bundled")):
            raise UserError(_("The rolls of a cut lay cannot change."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda l: l.lay_id.state in ("cut", "bundled")):
            raise UserError(_("The rolls of a cut lay cannot change."))
        return super().unlink()


class StockLot(models.Model):
    _inherit = "stock.lot"

    def _garment_roll_quants(self):
        self.ensure_one()
        return self.env["stock.quant"].sudo().search([
            ("lot_id", "=", self.id), ("location_id.usage", "=", "internal"), ("quantity", ">", 0)])

    def _garment_roll_available(self):
        """Metres of this roll in internal locations (product unit converted to metres when it is a length)."""
        self.ensure_one()
        qty = sum(self._garment_roll_quants().mapped("quantity"))
        meter = self.env.ref("uom.product_uom_meter")
        uom = self.product_id.uom_id
        if uom.category_id == meter.category_id:
            qty = uom._compute_quantity(qty, meter)
        return qty

    def _garment_roll_location(self):
        self.ensure_one()
        quants = self._garment_roll_quants().sorted(lambda q: -q.quantity)
        if quants:
            return quants[0].location_id
        warehouse = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", (self.company_id or self.env.company).id)], limit=1)
        return warehouse.lot_stock_id
