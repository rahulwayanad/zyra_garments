from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    garment_booking_line_id = fields.Many2one("garment.fabric.booking.line", string="Fabric Booking Line",
                                              index=True, copy=False, ondelete="set null")
    garment_booking_id = fields.Many2one(related="garment_booking_line_id.booking_id", string="Fabric Booking")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            self.sudo().order_line.garment_booking_line_id.booking_id._sync_state()
        return res
