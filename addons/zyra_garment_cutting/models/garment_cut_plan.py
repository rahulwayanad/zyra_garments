import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PLAN_STATES = [
    ("draft", "Draft"),
    ("approved", "Approved"),
    ("cutting", "Cutting"),
    ("done", "Done"),
    ("cancel", "Cancelled"),
]
OPEN_ORDER_STATES = ("confirmed", "in_production", "packed")


class GarmentCutPlan(models.Model):
    """Cut plan of one production order and colourway: what is to be cut per size (ordered + extra cut),
    the lays proposed from the markers to cover it, and the lays actually cut."""

    _name = "garment.cut.plan"
    _description = "Cut Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Plan", default="/", copy=False, readonly=True, index=True)
    state = fields.Selection(PLAN_STATES, default="draft", required=True, tracking=True, copy=False)
    company_id = fields.Many2one("res.company", related="order_id.company_id", store=True, index=True)
    order_id = fields.Many2one("garment.order", string="Order", required=True, index=True, check_company=True,
                               domain="[('state', 'in', %s)]" % (list(OPEN_ORDER_STATES),),
                               tracking=True)
    colour_id = fields.Many2one("garment.colour", string="Colourway", required=True, tracking=True)
    style_id = fields.Many2one(related="order_id.style_id", store=True)
    buyer_id = fields.Many2one(related="order_id.buyer_id", store=True, string="Buyer")
    techpack_id = fields.Many2one(related="order_id.techpack_id")
    allowed_colour_ids = fields.Many2many(related="order_id.colour_ids")
    fabric_id = fields.Many2one("product.product", string="Fabric", compute="_compute_fabric", store=True,
                                readonly=False, precompute=True)
    date_plan = fields.Date(string="Plan Date", default=fields.Date.context_today, required=True)
    planner_id = fields.Many2one("res.users", string="Planner", default=lambda self: self.env.user)
    extra_cut_pct = fields.Float(string="Extra Cut %", default=3.0, digits=(16, 2),
                                 help="Allowance cut above the ordered pieces, per size, rounded up.")
    max_plies = fields.Integer(string="Maximum Plies per Lay", default=80)
    end_allowance_m = fields.Float(string="End Allowance (m)", default=0.04, digits=(16, 3),
                                   help="Fabric lost at the ends of every ply.")
    bundle_size = fields.Integer(string="Pieces per Bundle", default=40,
                                 help="Largest bundle. 0 = one bundle per size and roll of each lay.")
    note = fields.Html()

    size_line_ids = fields.One2many("garment.cut.plan.size", "plan_id", string="Sizes", copy=False)
    proposal_ids = fields.One2many("garment.cut.plan.proposal", "plan_id", string="Proposed Lays", copy=False)
    lay_ids = fields.One2many("garment.lay", "plan_id", string="Lay Records", copy=False)

    qty_ordered = fields.Integer(string="Ordered", compute="_compute_totals", store=True)
    qty_to_cut = fields.Integer(string="To Cut", compute="_compute_totals", store=True)
    qty_planned = fields.Integer(string="Planned", compute="_compute_totals", store=True)
    qty_short = fields.Integer(string="Short", compute="_compute_totals", store=True)
    qty_overcut = fields.Integer(string="Overcut", compute="_compute_totals", store=True)
    qty_cut = fields.Integer(string="Cut by This Plan", compute="_compute_totals", store=True)
    planned_pct = fields.Float(string="Planned %", compute="_compute_totals", store=True, digits=(16, 1))
    fabric_to_lay = fields.Float(string="Fabric to Lay (m)", compute="_compute_totals", store=True,
                                 digits=(16, 2))
    fabric_required = fields.Float(string="Fabric Required", compute="_compute_totals", store=True,
                                   digits=(16, 2), help="Pieces to cut × tech pack consumption with wastage.")
    lay_count = fields.Integer(string="Lays", compute="_compute_lay_counts", store=True)
    lays_bundled = fields.Integer(string="Lays Bundled", compute="_compute_lay_counts", store=True)
    fabric_uom_name = fields.Char(related="fabric_id.uom_id.name", string="Fabric Unit")

    _sql_constraints = [
        ("extra_cut_range", "CHECK(extra_cut_pct >= 0 AND extra_cut_pct <= 50)",
         "Extra cut is a percentage between 0 and 50."),
        ("max_plies_positive", "CHECK(max_plies > 0)", "Maximum plies per lay must be above zero."),
        ("bundle_size_positive", "CHECK(bundle_size >= 0)", "Pieces per bundle cannot be negative."),
    ]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    def _fabric_line(self):
        """The tech pack fabric line for this colourway (colour-specific first, the biggest consumption)."""
        self.ensure_one()
        lines = self.techpack_id.bom_line_ids.filtered(
            lambda l: l.material_kind == "fabric" and (not l.colour_id or l.colour_id == self.colour_id))
        if self.fabric_id:
            same = lines.filtered(lambda l: l.product_id == self.fabric_id)
            lines = same or lines
        return lines.sorted(lambda l: (not l.colour_id, -l.consumption))[:1]

    @api.depends("order_id", "colour_id")
    def _compute_fabric(self):
        for plan in self:
            if plan.order_id and plan.colour_id:
                plan.fabric_id = plan._fabric_line().product_id or plan.fabric_id
            elif not plan.fabric_id:
                plan.fabric_id = False

    @api.depends("size_line_ids.qty_ordered", "size_line_ids.qty_to_cut", "size_line_ids.qty_planned",
                 "size_line_ids.qty_cut", "proposal_ids.fabric", "fabric_id", "colour_id")
    def _compute_totals(self):
        for plan in self:
            lines = plan.size_line_ids
            plan.qty_ordered = sum(lines.mapped("qty_ordered"))
            plan.qty_to_cut = sum(lines.mapped("qty_to_cut"))
            plan.qty_planned = sum(lines.mapped("qty_planned"))
            plan.qty_short = sum(max(l.qty_to_cut - l.qty_planned, 0) for l in lines)
            plan.qty_overcut = sum(max(l.qty_planned - l.qty_to_cut, 0) for l in lines)
            plan.qty_cut = sum(lines.mapped("qty_cut"))
            plan.planned_pct = plan.qty_to_cut and 100.0 * plan.qty_planned / plan.qty_to_cut or 0.0
            plan.fabric_to_lay = sum(plan.proposal_ids.mapped("fabric"))
            fabric_line = plan._fabric_line() if plan.order_id and plan.colour_id else False
            plan.fabric_required = plan.qty_to_cut * fabric_line.qty_with_wastage if fabric_line else 0.0

    @api.depends("lay_ids.state")
    def _compute_lay_counts(self):
        for plan in self:
            lays = plan.lay_ids.filtered(lambda l: l.state != "cancel")
            plan.lay_count = len(lays)
            plan.lays_bundled = len(lays.filtered(lambda l: l.state == "bundled"))

    @api.depends("name", "order_id.name", "colour_id.name")
    def _compute_display_name(self):
        for plan in self:
            plan.display_name = " · ".join(p for p in (plan.name, plan.order_id.name, plan.colour_id.name) if p)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.constrains("order_id", "colour_id", "state")
    def _check_order_colour(self):
        for plan in self:
            if plan.colour_id not in plan.order_id.colour_ids:
                raise ValidationError(_("Colourway %(colour)s is not on order %(order)s.",
                                        colour=plan.colour_id.name, order=plan.order_id.name))
            if plan.state != "cancel" and self.search_count([
                    ("id", "!=", plan.id), ("order_id", "=", plan.order_id.id),
                    ("colour_id", "=", plan.colour_id.id), ("state", "!=", "cancel")]):
                raise ValidationError(_("Order %(order)s already has an open cut plan for %(colour)s.",
                                        order=plan.order_id.name, colour=plan.colour_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.cut.plan") or "/"
        plans = super().create(vals_list)
        for plan in plans:
            if plan.order_id.state not in OPEN_ORDER_STATES:
                raise UserError(_("Order %s must be confirmed before cutting is planned.", plan.order_id.name))
        plans._sync_size_lines()
        return plans

    def write(self, vals):
        res = super().write(vals)
        if "order_id" in vals or "colour_id" in vals:
            self._sync_size_lines()
        return res

    def unlink(self):
        if self.lay_ids.filtered(lambda l: l.state in ("cut", "bundled")):
            raise UserError(_("A cut plan with cut lays cannot be deleted; cancel what is not cut instead."))
        return super().unlink()

    def _sync_size_lines(self):
        """One size line per size of the order (sorted by size), for this colourway."""
        for plan in self:
            sizes = plan.order_id.size_ids.sorted(lambda s: (s.sequence, s.id))
            existing = plan.size_line_ids
            existing.filtered(lambda l: l.size_id not in sizes).unlink()
            missing = sizes - existing.mapped("size_id")
            if missing:
                self.env["garment.cut.plan.size"].create([{"plan_id": plan.id, "size_id": s.id} for s in missing])

    # ------------------------------------------------------------------
    # Lay proposal
    # ------------------------------------------------------------------
    def _markers(self):
        self.ensure_one()
        return self.env["garment.marker"].search([
            ("style_id", "=", self.style_id.id),
            "|", ("colour_id", "=", False), ("colour_id", "=", self.colour_id.id),
            "|", ("company_id", "=", False), ("company_id", "=", self.company_id.id),
        ]).filtered(lambda m: m.pieces_per_ply > 0 and (not m.fabric_id or not self.fabric_id
                                                         or m.fabric_id == self.fabric_id))

    def _left_to_plan(self, exclude_open=True):
        """{size_id: pieces still to plan}. Proposals already turned into lays always count; open proposals
        (no lay yet) count unless ``exclude_open``, because the builder replaces them."""
        self.ensure_one()
        left = {l.size_id.id: l.qty_to_cut for l in self.size_line_ids}
        proposals = self.proposal_ids.filtered(lambda p: p.lay_id and p.lay_id.state != "cancel") \
            if exclude_open else self.proposal_ids
        for proposal in proposals:
            for size_id, ratio in proposal.marker_id._ratio_by_size().items():
                if size_id in left:
                    left[size_id] -= proposal.plies * ratio
        return left

    @api.model
    def _propose(self, left, markers, max_plies):
        """Greedy lay proposal. ``left`` {size_id: pieces}; returns [(marker, plies)] that never overcut.

        Each round takes the marker that cuts the most pieces without exceeding what is left of any of its
        sizes (plies capped at ``max_plies``); ties go to the better efficiency. With single-size markers in
        the set the sizes are covered exactly."""
        left = dict(left)
        result = []
        for _round in range(500):
            best = None
            for marker in markers:
                ratio = marker._ratio_by_size()
                if not ratio or any(size_id not in left for size_id in ratio):
                    continue
                plies = min(left[size_id] // r for size_id, r in ratio.items())
                plies = min(plies, max_plies)
                if plies <= 0:
                    continue
                key = (plies * marker.pieces_per_ply, marker.efficiency_pct, -marker.id)
                if not best or key > best[0]:
                    best = (key, marker, plies)
            if not best:
                break
            _key, marker, plies = best
            for size_id, r in marker._ratio_by_size().items():
                left[size_id] -= plies * r
            result.append((marker, plies))
        return result

    def _proposal_lines(self):
        """[(marker, plies)] covering what is left to plan (open proposals ignored)."""
        self.ensure_one()
        left = {k: max(v, 0) for k, v in self._left_to_plan(exclude_open=True).items()}
        return self._propose(left, self._markers(), self.max_plies)

    def action_propose(self):
        """Replace the open proposals by a fresh proposal from the markers."""
        for plan in self:
            if plan.state in ("done", "cancel"):
                raise UserError(_("Cut plan %s is closed.", plan.name))
            plan.proposal_ids.filtered(lambda p: not p.lay_id).unlink()
            lines = plan._proposal_lines()
            if not lines:
                raise UserError(_("No marker of style %s fits what is left to cut. Add or import markers.",
                                  plan.style_id.display_name))
            start = max(plan.proposal_ids.mapped("sequence") or [0])
            self.env["garment.cut.plan.proposal"].create([{
                "plan_id": plan.id, "sequence": start + i + 1, "marker_id": marker.id, "plies": plies,
            } for i, (marker, plies) in enumerate(lines)])
        return True

    def action_open_builder(self):
        self.ensure_one()
        if self.state in ("done", "cancel"):
            raise UserError(_("Cut plan %s is closed.", self.name))
        builder = self.env["garment.cut.plan.builder"]._create_for_plan(self)
        return builder._action_open()

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------
    def action_approve(self):
        for plan in self:
            if plan.state not in ("draft", "approved", "cutting"):
                raise UserError(_("Only a draft or running cut plan can be approved."))
            new = plan.proposal_ids.filtered(lambda p: not p.lay_id)
            if not new and plan.state == "draft":
                raise UserError(_("Propose at least one lay before approving cut plan %s.", plan.name))
            for proposal in new:
                if proposal.plies <= 0:
                    raise UserError(_("Every proposed lay needs plies above zero."))
                if proposal.plies > plan.max_plies:
                    raise UserError(_("Lay %(seq)s has %(plies)s plies; the plan allows %(max)s per lay.",
                                      seq=proposal.sequence, plies=proposal.plies, max=plan.max_plies))
            new.marker_id._garment_check_usable()
            new._create_lay()
            if plan.state == "draft":
                plan.state = "approved"
        return True

    def action_done(self):
        for plan in self:
            if plan.lay_ids.filtered(lambda l: l.state in ("spread", "cut")):
                raise UserError(_("Bundle or cancel the lays on the table before closing cut plan %s.",
                                  plan.name))
            plan.lay_ids.filtered(lambda l: l.state == "planned").write({"state": "cancel"})
            plan.state = "done"
        return True

    def action_cancel(self):
        for plan in self:
            if plan.lay_ids.filtered(lambda l: l.state in ("cut", "bundled")):
                raise UserError(_("Cut plan %s already has cut lays; close it with Done instead.", plan.name))
            plan.lay_ids.write({"state": "cancel"})
            plan.state = "cancel"
        return True

    def action_draft(self):
        for plan in self.filtered(lambda p: p.state == "cancel"):
            plan.lay_ids.unlink()
            plan.proposal_ids.unlink()
            plan.state = "draft"
        return True

    def _update_state_from_lays(self):
        """approved → cutting at the first cut lay; → done when every lay is bundled and nothing is short."""
        for plan in self:
            lays = plan.lay_ids.filtered(lambda l: l.state != "cancel")
            if plan.state == "approved" and lays.filtered(lambda l: l.state in ("cut", "bundled")):
                plan.state = "cutting"
            if plan.state in ("approved", "cutting") and lays \
                    and all(l.state == "bundled" for l in lays) and not plan.qty_short:
                plan.state = "done"

    def action_view_lays(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_cutting.action_garment_lay")
        action["domain"] = [("plan_id", "=", self.id)]
        action["context"] = {"default_plan_id": self.id}
        return action

    def action_view_bundles(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_cutting.action_garment_bundle")
        action["domain"] = [("plan_id", "=", self.id)]
        action["context"] = {}
        return action


class GarmentCutPlanSize(models.Model):
    _name = "garment.cut.plan.size"
    _description = "Cut Plan Size"
    _order = "plan_id, size_sequence, id"

    plan_id = fields.Many2one("garment.cut.plan", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True)
    size_id = fields.Many2one("garment.size", required=True)
    size_sequence = fields.Integer(related="size_id.sequence", store=True)
    qty_ordered = fields.Integer(string="Ordered", compute="_compute_qty", store=True)
    qty_to_cut = fields.Integer(string="To Cut", compute="_compute_qty", store=True)
    qty_planned = fields.Integer(string="Planned", compute="_compute_qty", store=True)
    qty_left = fields.Integer(string="Left to Plan", compute="_compute_qty", store=True)
    qty_cut = fields.Integer(string="Cut", compute="_compute_qty", store=True)

    @api.depends("plan_id.order_id.line_ids.qty_ordered", "plan_id.colour_id", "plan_id.extra_cut_pct",
                 "plan_id.proposal_ids.plies", "plan_id.proposal_ids.marker_id",
                 "plan_id.proposal_ids.lay_id.state",
                 "plan_id.lay_ids.state", "plan_id.lay_ids.plies_actual", "plan_id.lay_ids.marker_id")
    def _compute_qty(self):
        for line in self:
            plan = line.plan_id
            cell = plan.order_id.line_ids.filtered(
                lambda c: c.colour_id == plan.colour_id and c.size_id == line.size_id)
            ordered = sum(cell.mapped("qty_ordered"))
            line.qty_ordered = ordered
            # Round up per size; the float guard keeps 100 × 1.03 at 103 rather than 104.
            line.qty_to_cut = int(math.ceil(round(ordered * (1.0 + plan.extra_cut_pct / 100.0), 6)))
            planned = 0
            for proposal in plan.proposal_ids:
                if proposal.lay_id and proposal.lay_id.state == "cancel":
                    continue
                planned += proposal.plies * proposal.marker_id._ratio_by_size().get(line.size_id.id, 0)
            line.qty_planned = planned
            line.qty_left = max(line.qty_to_cut - planned, 0)
            cut = 0
            for lay in plan.lay_ids.filtered(lambda l: l.state in ("cut", "bundled")):
                cut += lay.plies_actual * lay.marker_id._ratio_by_size().get(line.size_id.id, 0)
            line.qty_cut = cut


class GarmentCutPlanProposal(models.Model):
    """One proposed lay of a cut plan: a marker and its plies. Approving the plan turns it into a lay."""

    _name = "garment.cut.plan.proposal"
    _description = "Proposed Lay"
    _order = "plan_id, sequence, id"

    plan_id = fields.Many2one("garment.cut.plan", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True)
    sequence = fields.Integer(string="#", default=1)
    marker_id = fields.Many2one("garment.marker", required=True, ondelete="restrict")
    ratio_text = fields.Char(related="marker_id.ratio_text", string="Size Ratio")
    ratio_short = fields.Char(related="marker_id.ratio_short", string="Ratio")
    plies = fields.Integer(required=True, default=1)
    pieces = fields.Integer(compute="_compute_figures", store=True)
    lay_length = fields.Float(related="marker_id.length_m", string="Lay Length (m)", digits=(16, 3))
    fabric = fields.Float(string="Fabric (m)", compute="_compute_figures", store=True, digits=(16, 2))
    lay_id = fields.Many2one("garment.lay", string="Lay", readonly=True, copy=False, ondelete="set null")

    @api.depends("plies", "marker_id.pieces_per_ply", "marker_id.length_m", "plan_id.end_allowance_m")
    def _compute_figures(self):
        for proposal in self:
            proposal.pieces = proposal.plies * proposal.marker_id.pieces_per_ply
            proposal.fabric = proposal.plies * (proposal.marker_id.length_m + proposal.plan_id.end_allowance_m)

    def write(self, vals):
        if self.filtered("lay_id") and set(vals) & {"marker_id", "plies"}:
            raise UserError(_("This lay is already on the cutting floor; change the lay itself."))
        return super().write(vals)

    def _create_lay(self):
        Lay = self.env["garment.lay"]
        for proposal in self:
            plan = proposal.plan_id
            proposal.lay_id = Lay.create({
                "plan_id": plan.id,
                "marker_id": proposal.marker_id.id,
                "plies_planned": proposal.plies,
                "lay_length": proposal.marker_id.length_m,
                "end_allowance_m": plan.end_allowance_m,
                "bundle_size": plan.bundle_size,
            })
        return True
