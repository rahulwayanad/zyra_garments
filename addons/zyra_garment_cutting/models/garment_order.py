from odoo import _, fields, models
from odoo.exceptions import UserError


class GarmentOrder(models.Model):
    _inherit = "garment.order"

    cut_plan_ids = fields.One2many("garment.cut.plan", "order_id", string="Cut Plans")
    cut_plan_count = fields.Integer(compute="_compute_cutting_counts", string="Cut Plans")
    bundle_count = fields.Integer(compute="_compute_cutting_counts", string="Bundles")

    def _compute_cutting_counts(self):
        Bundle = self.env["garment.bundle"]
        counts = dict(Bundle._read_group([("order_id", "in", self.ids)], ["order_id"], ["__count"]))
        for order in self:
            order.cut_plan_count = len(order.cut_plan_ids.filtered(lambda p: p.state != "cancel"))
            order.bundle_count = counts.get(order._origin, 0)

    def action_propose_cut_plan(self):
        """Screen 2: open a cut plan per colourway that has none and propose its lays from the markers."""
        self.ensure_one()
        if self.state not in ("confirmed", "in_production", "packed"):
            raise UserError(_("Confirm order %s before planning the cut.", self.name))
        Plan = self.env["garment.cut.plan"]
        open_plans = self.cut_plan_ids.filtered(lambda p: p.state != "cancel")
        new = Plan
        for colour in self.colour_ids:
            pieces = sum(self.line_ids.filtered(lambda l: l.colour_id == colour).mapped("qty_ordered"))
            if not pieces or colour in open_plans.mapped("colour_id"):
                continue
            plan = Plan.create({"order_id": self.id, "colour_id": colour.id})
            if plan._proposal_lines():
                plan.action_propose()
            new |= plan
        plans = (open_plans | new)
        if not plans:
            raise UserError(_("Order %s has no pieces to cut.", self.name))
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_cutting.action_garment_cut_plan")
        if len(new) == 1 or len(plans) == 1:
            action.update({"views": [(False, "form")], "view_mode": "form", "res_id": (new or plans).id})
        else:
            action["domain"] = [("id", "in", plans.ids)]
            action["context"] = {}
        return action

    def action_view_bundles(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_cutting.action_garment_bundle")
        action["domain"] = [("order_id", "=", self.id)]
        action["context"] = {}
        return action
