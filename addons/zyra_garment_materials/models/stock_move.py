from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        moves._garment_tag_received_rolls()
        return moves

    def _garment_tag_received_rolls(self):
        """A roll received against a booked purchase line becomes a fabric roll of that booking: received
        length, date, promised date and supplier are written on the lot."""
        bookings = self.env["garment.fabric.booking"]
        for move in self.filtered(lambda m: m.state == "done" and m.purchase_line_id.garment_booking_line_id):
            pol = move.purchase_line_id
            booking_line = pol.garment_booking_line_id
            for ml in move.move_line_ids.filtered("lot_id"):
                lot = ml.lot_id.sudo()
                if lot.booking_line_id and lot.booking_line_id != booking_line:
                    continue
                qty = ml.product_uom_id._compute_quantity(ml.quantity, move.product_id.uom_id, round=False)
                vals = {
                    "booking_line_id": booking_line.id,
                    "roll_received_qty": (lot.roll_received_qty or 0.0) + qty,
                    "roll_received_date": lot.roll_received_date or fields.Date.context_today(self),
                    "roll_promised_date": lot.roll_promised_date or (pol.date_planned and pol.date_planned.date()),
                    "roll_supplier_id": lot.roll_supplier_id.id or pol.order_id.partner_id.id,
                }
                if booking_line.material_kind == "fabric":
                    vals["is_fabric_roll"] = True
                lot.write(vals)
            bookings |= booking_line.booking_id
        if bookings:
            bookings.sudo()._sync_state()
        return True
