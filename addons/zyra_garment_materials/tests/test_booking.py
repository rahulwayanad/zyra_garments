from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import MaterialsCase


@tagged("post_install", "-at_install", "zyra")
class TestBooking(MaterialsCase):

    def _booking(self, booking_of="fabric", confirm=True):
        booking = self.env["garment.fabric.booking"].create({"order_id": self.order.id, "booking_of": booking_of})
        if confirm:
            booking.action_confirm()
        return booking

    def _line(self, booking, colour):
        return booking.line_ids.filtered(lambda l: l.colour_id == colour)

    def test_required_is_pieces_x_consumption_x_one_plus_wastage_per_colourway(self):
        booking = self._booking(confirm=False)
        self.assertEqual(len(booking.line_ids), 2, "one fabric line per colourway; trims are not on a fabric booking")
        red = self._line(booking, self.red)
        self.assertEqual(red.order_pieces, 200)
        self.assertAlmostEqual(red.consumption, 1.2, places=4)
        self.assertAlmostEqual(red.wastage_pct, 5.0, places=2)
        self.assertAlmostEqual(red.qty_required, 252.0, places=2)
        self.assertTrue(booking.name.startswith("FB/"))

    def test_trim_used_on_every_colourway_is_one_all_line(self):
        booking = self._booking("trims", confirm=False)
        self.assertEqual(len(booking.line_ids), 1)
        line = booking.line_ids
        self.assertFalse(line.colour_id)
        self.assertEqual(line.colour_label, "All")
        self.assertEqual(line.order_pieces, 400)
        self.assertAlmostEqual(line.qty_required, 800.0)

    def test_needed_date_defaults_three_weeks_before_ex_factory(self):
        booking = self._booking(confirm=False)
        self.assertEqual(booking.date_needed, self.order.ex_factory_date - timedelta(days=21))

    def test_shortfall_to_order_is_required_minus_in_stock_minus_open_po(self):
        booking = self._booking()
        red = self._line(booking, self.red)
        self.assertAlmostEqual(red.qty_to_order, 252.0)
        self.make_roll("RB-1", 100.0, red)
        self.make_roll("RB-2", 52.0, red)
        self.assertAlmostEqual(red.qty_in_stock, 152.0)
        self.assertAlmostEqual(red.qty_to_order, 100.0)
        self.assertAlmostEqual(red.value_to_order, 200.0)
        self.assertFalse(red.is_in_house)
        self.assertAlmostEqual(booking.value_to_order, 200.0 + 252.0 * 2.0)
        self.assertEqual(self.env["garment.fabric.booking.line"]._formula_to_order(252, 152, 120), 0.0)

    def test_rejected_roll_does_not_count_as_in_house(self):
        booking = self._booking()
        red = self._line(booking, self.red)
        roll = self.make_roll("RB-REJ", 252.0, red)
        self.assertTrue(red.is_in_house)
        roll.action_roll_reject("Holes")
        self.assertFalse(red.is_in_house)
        self.assertAlmostEqual(red.qty_to_order, 252.0)

    def test_raise_pos_creates_one_rfq_per_vendor_linked_to_the_lines(self):
        booking = self._booking()
        self._line(booking, self.red)
        self.make_roll("RB-PO", 52.0, self._line(booking, self.red))
        booking.with_user(self.store).action_raise_pos()
        pos = booking._purchase_orders()
        self.assertEqual(len(pos), 1)
        self.assertEqual(pos.partner_id, self.vendor)
        self.assertEqual(pos.origin, booking.name)
        red_pol = pos.order_line.filtered(lambda l: l.garment_booking_line_id.colour_id == self.red)
        self.assertAlmostEqual(red_pol.product_qty, 200.0)
        self.assertEqual(booking.state, "ordered")
        red = self._line(booking, self.red)
        self.assertAlmostEqual(red.qty_open_po, 200.0)
        self.assertAlmostEqual(red.qty_to_order, 0.0)
        with self.assertRaises(UserError):
            booking.action_raise_pos()  # nothing left to order

    def test_raise_pos_needs_a_confirmed_booking_and_a_vendor(self):
        booking = self._booking(confirm=False)
        with self.assertRaises(UserError):
            booking.action_raise_pos()
        booking.action_confirm()
        self.fabric.seller_ids.unlink()
        with self.assertRaises(UserError):
            booking.action_raise_pos()

    def test_receipt_of_booked_po_tags_rolls_and_puts_the_booking_in_house(self):
        booking = self._booking()
        booking.action_raise_pos()
        po = booking._purchase_orders()
        po.button_confirm()
        picking = po.picking_ids
        for index, move in enumerate(picking.move_ids):
            move.move_line_ids.unlink()
            self.env["stock.move.line"].create({
                "move_id": move.id, "picking_id": picking.id, "product_id": move.product_id.id,
                "product_uom_id": move.product_uom.id, "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id, "lot_name": "RB-RCV-%s" % index,
                "quantity": move.product_uom_qty})
            move.picked = True
        picking._action_done()
        rolls = booking.roll_ids
        self.assertEqual(len(rolls), 2)
        self.assertTrue(all(rolls.mapped("is_fabric_roll")))
        self.assertEqual(rolls.roll_supplier_id, self.vendor)
        self.assertEqual(rolls.garment_order_id, self.order)
        self.assertAlmostEqual(sum(rolls.mapped("roll_received_qty")), 504.0)
        self.assertEqual(booking.state, "in_house")
        self.assertEqual(booking.date_in_house, self.today)
        self.assertEqual(booking.in_house_pct, 100.0)
        # a roll rejected later takes the booking out of "in house"
        rolls[0].action_roll_reject("Shade bars")
        self.assertEqual(booking.state, "ordered")

    def test_untracked_trims_count_purchase_receipts_as_in_stock(self):
        booking = self._booking("trims")
        booking.action_raise_pos()
        po = booking._purchase_orders()
        po.button_confirm()
        move = po.picking_ids.move_ids
        move.quantity = 500
        move.picked = True
        po.picking_ids.with_context(cancel_backorder=False)._action_done()
        line = booking.line_ids
        self.assertAlmostEqual(line.qty_in_stock, 500.0)
        self.assertAlmostEqual(line.qty_open_po, 300.0)
        self.assertAlmostEqual(line.qty_to_order, 0.0)

    def test_booking_is_short_when_needed_date_passed_and_not_in_house(self):
        booking = self._booking()
        self.assertFalse(booking.is_short)
        booking.date_needed = self.today - timedelta(days=1)
        self.assertTrue(booking.is_short)
        self.assertEqual(booking.shortage, "short")
        self.assertIn(booking, self.env["garment.fabric.booking"].search([("is_short", "=", True)]))
        for colour in (self.red, self.blue):
            self.make_roll("RB-S-%s" % colour.code, 252.0, self._line(booking, colour))
        self.assertFalse(booking.is_short)
        self.assertEqual(booking.state, "in_house")

    def test_in_house_pct_is_received_over_required(self):
        booking = self._booking()
        self.make_roll("RB-P1", 252.0, self._line(booking, self.red))
        self.make_roll("RB-P2", 300.0, self._line(booking, self.blue))  # over-receipt counts up to required
        self.assertAlmostEqual(booking.in_house_pct, 100.0)
        booking2 = self.env["garment.fabric.booking"]
        self.assertAlmostEqual(booking2._formula_in_house_pct(126, 504), 25.0)

    def test_order_fabric_in_house_tile_is_fabric_received_over_required(self):
        self.assertFalse(self.order.has_fabric_booking)
        booking = self._booking()
        self._booking("trims")
        self.make_roll("RB-T1", 126.0, self._line(booking, self.red))
        self.order.invalidate_recordset(["fabric_in_house_pct", "has_fabric_booking"])
        self.assertTrue(self.order.has_fabric_booking)
        self.assertAlmostEqual(self.order.fabric_in_house_pct, 25.0)
        self.assertEqual(len(self.order.fabric_booking_line_ids), 2)

    def test_issued_fabric_is_received_minus_on_hand(self):
        booking = self._booking()
        red = self._line(booking, self.red)
        roll = self.make_roll("RB-ISS", 100.0, red)
        self.env["stock.quant"]._update_available_quantity(self.fabric, self.warehouse.lot_stock_id, -60.0, lot_id=roll)
        self.assertAlmostEqual(red.qty_on_hand, 40.0)
        self.assertAlmostEqual(red.qty_used, 60.0)
        self.assertAlmostEqual(red.qty_in_stock, 100.0, msg="cutting does not reduce what is in house")

    def test_only_draft_bookings_reload_or_delete(self):
        booking = self._booking()
        with self.assertRaises(UserError):
            booking.action_load_requirements()
        with self.assertRaises(UserError):
            booking.unlink()

    def test_confirm_needs_materials(self):
        booking = self._booking(confirm=False)
        booking.line_ids.unlink()
        with self.assertRaises(UserError):
            booking.action_confirm()

    def test_booking_form_from_order(self):
        with Form(self.env["garment.fabric.booking"]) as form:
            form.order_id = self.order
        booking = form.save()
        self.assertEqual(booking.buyer_id, self.buyer)
        self.assertEqual(len(booking.line_ids), 2)

    def test_reports_render(self):
        booking = self._booking()
        roll = self.make_roll("RB-REP", 50.0, self._line(booking, self.red))
        insp = self.env["garment.fabric.inspection"].create({"lot_id": roll.id})
        for xmlid, records in (("action_report_fabric_booking", booking),
                               ("action_report_fabric_inspection", insp),
                               ("action_report_roll_label", roll)):
            html, _fmt = self.env["ir.actions.report"]._render_qweb_html(
                "zyra_garment_materials." + xmlid, records.ids)
            self.assertIn(records[0].name.encode(), html)
