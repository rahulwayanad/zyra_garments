from odoo import _, api, fields, models


class GarmentOrder(models.Model):
    _inherit = "garment.order"

    pack_plan_ids = fields.One2many("garment.pack.plan", "order_id", string="Pack Plans")
    shipment_ids = fields.Many2many("garment.shipment", string="Shipments", compute="_compute_garment_shipping")
    garment_cartons_planned = fields.Integer(string="Cartons Planned", compute="_compute_garment_shipping")
    garment_cartons_packed = fields.Integer(string="Cartons Packed", compute="_compute_garment_shipping")

    @api.depends("pack_plan_ids.cartons_planned", "pack_plan_ids.cartons_packed")
    def _compute_garment_shipping(self):
        Shipment = self.env["garment.shipment"]
        for order in self:
            plans = order.pack_plan_ids
            order.garment_cartons_planned = sum(max(p.cartons_planned, p.carton_count) for p in plans)
            order.garment_cartons_packed = sum(plans.mapped("cartons_packed"))
            order.shipment_ids = Shipment.search([("order_ids", "in", order.ids)]) if order.id else Shipment

    def _garment_shipping_final_ok(self):
        """True when shipping may go ahead as far as quality is concerned.

        Soft dependency on zyra_garment_quality: reads ``final_passed`` only if that field exists."""
        self.ensure_one()
        if "final_passed" not in self._fields:
            return True
        return bool(self.final_passed)

    def action_garment_pack_plan(self):
        """Open the order's pack plan (a new one, filled from the order, when there is none)."""
        self.ensure_one()
        plans = self.pack_plan_ids
        action = {
            "type": "ir.actions.act_window",
            "name": _("Pack Plan"),
            "res_model": "garment.pack.plan",
            "context": {"default_order_id": self.id},
        }
        if len(plans) == 1:
            action.update(view_mode="form", res_id=plans.id)
        elif plans:
            action.update(view_mode="list,form", domain=[("id", "in", plans.ids)])
        else:
            action.update(view_mode="form")
        return action
