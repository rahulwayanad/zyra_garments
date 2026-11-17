from datetime import timedelta

from odoo import api, fields, models


class GarmentOrder(models.Model):
    _inherit = "garment.order"

    fabric_booking_ids = fields.One2many("garment.fabric.booking", "order_id", string="Bookings")
    fabric_booking_count = fields.Integer(string="Booking Count", compute="_compute_fabric_in_house")
    has_fabric_booking = fields.Boolean(compute="_compute_fabric_in_house")
    fabric_in_house_pct = fields.Float(string="Fabric In House %", digits=(16, 0),
                                       compute="_compute_fabric_in_house",
                                       help="Fabric received ÷ fabric required on the order's fabric bookings.")
    fabric_booking_line_ids = fields.Many2many("garment.fabric.booking.line", string="Fabric Reconciliation",
                                               compute="_compute_fabric_in_house")

    def _garment_fabric_needed_date(self):
        """Fabric should be in house three weeks before ex-factory (or by the order date if later)."""
        self.ensure_one()
        if not self.ex_factory_date:
            return False
        needed = self.ex_factory_date - timedelta(days=21)
        return max(needed, self.date_order) if self.date_order else needed

    @api.depends("fabric_booking_ids.line_ids")
    def _compute_fabric_in_house(self):
        for order in self:
            bookings = order.sudo().fabric_booking_ids
            fabric = bookings.filtered(lambda b: b.booking_of == "fabric")
            lines = fabric.line_ids
            required = sum(lines.mapped("qty_required"))
            received = sum(min(l.qty_in_stock, l.qty_required) for l in lines)
            order.fabric_booking_count = len(bookings)
            order.has_fabric_booking = bool(fabric)
            order.fabric_in_house_pct = (
                self.env["garment.fabric.booking"]._formula_in_house_pct(received, required) if lines else 0.0)
            order.fabric_booking_line_ids = lines

    def action_view_fabric_bookings(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_materials.action_garment_fabric_booking")
        action["domain"] = [("order_id", "=", self.id)]
        action["context"] = {"default_order_id": self.id}
        return action
