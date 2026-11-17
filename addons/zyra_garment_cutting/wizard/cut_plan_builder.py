from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GarmentCutPlanBuilder(models.TransientModel):
    """Cut plan builder (screen 48): lays proposed from the markers to cover what is left per size;
    plies are edited before the plan is approved."""

    _name = "garment.cut.plan.builder"
    _description = "Cut Plan Builder"

    plan_id = fields.Many2one("garment.cut.plan", required=True, ondelete="cascade")
    name = fields.Char(compute="_compute_name")
    line_ids = fields.One2many("garment.cut.plan.builder.line", "builder_id", string="Proposed Lay Lines")
    left_to_plan = fields.Integer(compute="_compute_figures")
    lay_count = fields.Integer(string="Proposed Lays", compute="_compute_figures")
    pieces = fields.Integer(string="Pieces Proposed", compute="_compute_figures")
    fabric = fields.Float(string="Fabric (m)", compute="_compute_figures", digits=(16, 1))
    sizes_html = fields.Html(compute="_compute_figures", sanitize=False)

    @api.depends("plan_id.name")
    def _compute_name(self):
        for builder in self:
            builder.name = _("%s · Builder", builder.plan_id.name or "")

    @api.depends("line_ids.plies", "line_ids.marker_id", "plan_id")
    def _compute_figures(self):
        for builder in self:
            plan = builder.plan_id
            left = plan._left_to_plan(exclude_open=True) if plan else {}
            for line in builder.line_ids:
                for size_id, ratio in line.marker_id._ratio_by_size().items():
                    if size_id in left:
                        left[size_id] -= (line.plies or 0) * ratio
            builder.left_to_plan = sum(max(v, 0) for v in left.values())
            builder.lay_count = len(builder.line_ids.filtered(lambda l: l.plies > 0))
            builder.pieces = sum(builder.line_ids.mapped("pieces"))
            builder.fabric = sum(builder.line_ids.mapped("fabric"))
            builder.sizes_html = builder._sizes_table(left)

    def _sizes_table(self, left):
        plan = self.plan_id
        if not plan:
            return False
        lines = plan.size_line_ids.sorted(lambda l: (l.size_id.sequence, l.size_id.id))
        head = Markup("").join(Markup('<th class="text-end">%s</th>') % l.size_id.name for l in lines)
        ordered = Markup("").join(Markup('<td class="text-end">{:,}</td>'.format(l.qty_ordered)) for l in lines)
        lefts = []
        for l in lines:
            value = left.get(l.size_id.id, 0)
            css = "text-end text-danger" if value < 0 else "text-end"
            lefts.append(Markup('<td class="%s">{:,}</td>'.format(value)) % css)
        total_left = sum(left.values())
        return Markup(
            '<table class="table table-sm o_zyra_size_table"><thead><tr><th>%s</th>%s<th class="text-end">%s</th>'
            '</tr></thead><tbody><tr><td>%s</td>%s<td class="text-end">{:,}</td></tr>'
            '<tr><td>%s</td>%s<td class="text-end fw-bold">{:,}</td></tr></tbody></table>'.format(
                plan.qty_ordered, total_left)
        ) % (escape(_("Size")), head, escape(_("Total")), escape(_("Ordered")), ordered,
             escape(_("Left to plan")), Markup("").join(lefts))

    # ------------------------------------------------------------------
    @api.model
    def _create_for_plan(self, plan):
        """Builder pre-filled with the plan's open proposals, or a fresh proposal when there are none."""
        open_proposals = plan.proposal_ids.filtered(lambda p: not p.lay_id)
        if open_proposals:
            lines = [(p.marker_id, p.plies) for p in open_proposals]
        else:
            lines = plan._proposal_lines()
        return self.create({
            "plan_id": plan.id,
            "line_ids": [(0, 0, {"sequence": i + 1, "marker_id": m.id, "plies": p}) for i, (m, p) in enumerate(lines)],
        })

    def _action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_repropose(self):
        self.ensure_one()
        self.line_ids.unlink()
        lines = self.plan_id._proposal_lines()
        if not lines:
            raise UserError(_("No marker fits what is left to cut. Import or add markers first."))
        self.write({"line_ids": [(0, 0, {"sequence": i + 1, "marker_id": m.id, "plies": p})
                                 for i, (m, p) in enumerate(lines)]})
        return self._action_open()

    def _save_proposals(self):
        self.ensure_one()
        plan = self.plan_id
        plan.proposal_ids.filtered(lambda p: not p.lay_id).unlink()
        start = max(plan.proposal_ids.mapped("sequence") or [0])
        self.env["garment.cut.plan.proposal"].create([{
            "plan_id": plan.id, "sequence": start + i + 1, "marker_id": line.marker_id.id, "plies": line.plies,
        } for i, line in enumerate(self.line_ids.filtered(lambda l: l.plies > 0).sorted("sequence"))])

    def action_save(self):
        self._save_proposals()
        return self._back_to_plan()

    def action_approve(self):
        self.ensure_one()
        if not self.line_ids.filtered(lambda l: l.plies > 0) and self.plan_id.state == "draft":
            raise UserError(_("Propose at least one lay before approving."))
        self._save_proposals()
        self.plan_id.action_approve()
        return self._back_to_plan()

    def _back_to_plan(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "garment.cut.plan",
            "res_id": self.plan_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_import_markers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Markers (CSV)"),
            "res_model": "garment.marker.import",
            "view_mode": "form",
            "target": "new",
            "context": {"default_style_id": self.plan_id.style_id.id, "default_fabric_id": self.plan_id.fabric_id.id,
                        "default_builder_id": self.id},
        }


class GarmentCutPlanBuilderLine(models.TransientModel):
    _name = "garment.cut.plan.builder.line"
    _description = "Cut Plan Builder Lay"
    _order = "sequence, id"

    builder_id = fields.Many2one("garment.cut.plan.builder", required=True, ondelete="cascade")
    style_id = fields.Many2one(related="builder_id.plan_id.style_id")
    sequence = fields.Integer(string="#", default=1)
    marker_id = fields.Many2one("garment.marker", required=True, domain="[('style_id', '=', style_id)]")
    ratio_text = fields.Char(related="marker_id.ratio_text", string="Size Ratio")
    plies = fields.Integer(string="Plies (edit)", default=1)
    pieces = fields.Integer(compute="_compute_figures")
    lay_length = fields.Float(related="marker_id.length_m", string="Lay Length", digits=(16, 3))
    fabric = fields.Float(compute="_compute_figures", digits=(16, 2))

    @api.depends("plies", "marker_id.pieces_per_ply", "marker_id.length_m", "builder_id.plan_id.end_allowance_m")
    def _compute_figures(self):
        for line in self:
            line.pieces = (line.plies or 0) * line.marker_id.pieces_per_ply
            line.fabric = (line.plies or 0) * (line.marker_id.length_m + line.builder_id.plan_id.end_allowance_m)
