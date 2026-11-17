from odoo import models

STATE_EVENTS = {"confirmed": "order.confirmed", "shipped": "order.shipped"}


class GarmentOrder(models.Model):
    _inherit = "garment.order"

    def write(self, vals):
        before = {o.id: o.state for o in self} if "state" in vals else {}
        res = super().write(vals)
        event = STATE_EVENTS.get(vals.get("state"))
        if event:
            for order in self.filtered(lambda o: before.get(o.id) != o.state):
                self.env["garment.webhook"].sudo()._garment_emit(event, {
                    "order_id": order.id, "order": order.name, "buyer_po": order.buyer_po or None,
                    "qty_ordered": order.qty_ordered}, company=order.company_id)
        return res
