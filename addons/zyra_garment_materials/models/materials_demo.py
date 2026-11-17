"""Demo loader for materials: bookings for the merchandising demo orders, rolls received through purchase
orders in every status, and 4-point inspections (one that put a roll on hold for shade, one over the limit,
one reject, one still on the tablet). Dates are relative to the install day."""
from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Command

B = "zyra_garment_base."
T = "zyra_techpack."
M = "zyra_garment_merch."
X = "zyra_garment_materials."

WIDTH_CM = {"FAB-SJ-180": 182.0, "FAB-POP-SKY": 147.0, "FAB-DNM-12": 150.0, "FAB-TWL-240": 148.0, "FAB-PKT-110": 112.0}
GSM = {"FAB-SJ-180": 180.0, "FAB-POP-SKY": 115.0, "FAB-DNM-12": 405.0, "FAB-TWL-240": 240.0, "FAB-PKT-110": 110.0}


class GarmentMaterialsDemo(models.AbstractModel):
    _name = "garment.materials.demo"
    _description = "Materials demo loader"

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _xmlid(self, record, name):
        self.env["ir.model.data"]._update_xmlids([{"xml_id": X + name, "record": record, "noupdate": True}])

    # ------------------------------------------------------------------
    def _ensure_vendors(self, bookings):
        delta = self._ref(B + "partner_supplier_delta_weave")
        denim = self._ref(X + "partner_supplier_ridgeline_denim")
        trims = self._ref(X + "partner_supplier_coastal_trims")
        for product in bookings.line_ids.product_id:
            if product.seller_ids:
                continue
            if product == self._ref(B + "product_fabric_denim"):
                vendor = denim
            elif product.tracking == "lot":
                vendor = delta
            else:
                vendor = trims
            product.product_tmpl_id.seller_ids = [Command.create({
                "partner_id": vendor.id, "price": product.standard_price or 1.0, "delay": 21})]

    def _booking(self, xmlid, order, booking_of="fabric", needed=None, confirm=True, user=None):
        booking = self.env["garment.fabric.booking"].create({
            "order_id": order.id,
            "booking_of": booking_of,
            "booking_date": order.date_order + timedelta(days=3),
            "user_id": (user or self._ref(B + "user_vivek") or self.env.user).id,
        })
        if needed is not None:
            booking.date_needed = fields.Date.context_today(self) + timedelta(days=needed)
        self._xmlid(booking, xmlid)
        if confirm:
            booking.action_confirm()
        return booking

    def _receive(self, booking, share=1.0, roll_size=150.0, received_days=-30, only=None):
        """Raise the POs of ``booking`` and receive ``share`` of each line, in rolls of ``roll_size``."""
        self._ensure_vendors(booking)
        booking.action_raise_pos()
        orders = booking._purchase_orders()
        orders.button_confirm()
        today = fields.Date.context_today(self)
        rolls = self.env["stock.lot"]
        for picking in orders.picking_ids.filtered(lambda p: p.state not in ("done", "cancel")):
            for move in picking.move_ids:
                line = move.purchase_line_id.garment_booking_line_id
                if only and line not in only:
                    qty_total = 0.0
                else:
                    qty_total = round(move.product_uom_qty * share, 2)
                move.move_line_ids.unlink()
                if qty_total <= 0:
                    continue
                if move.product_id.tracking == "lot":
                    remaining = qty_total
                    while remaining > 0.01:
                        qty = min(roll_size, remaining)
                        remaining = round(remaining - qty, 2)
                        name = self._next_roll_name()
                        self.env["stock.move.line"].create({
                            "move_id": move.id, "picking_id": picking.id, "product_id": move.product_id.id,
                            "product_uom_id": move.product_uom.id, "location_id": move.location_id.id,
                            "location_dest_id": move.location_dest_id.id, "lot_name": name, "quantity": qty,
                        })
                else:
                    self.env["stock.move.line"].create({
                        "move_id": move.id, "picking_id": picking.id, "product_id": move.product_id.id,
                        "product_uom_id": move.product_uom.id, "location_id": move.location_id.id,
                        "location_dest_id": move.location_dest_id.id, "quantity": qty_total,
                    })
                move.picked = True
            picking.move_ids.filtered(lambda m: not m.move_line_ids).picked = False
            if picking.move_ids.filtered("picked"):
                picking.with_context(cancel_backorder=False)._action_done()
        rolls = booking.roll_ids
        for index, roll in enumerate(rolls.sorted("name")):
            code = roll.product_id.default_code or ""
            roll.write({
                "roll_received_date": today + timedelta(days=received_days + index % 3),
                "roll_promised_date": today + timedelta(days=received_days + 1),
                "dye_lot": "DL-%04d" % (4200 + (roll.booking_line_id.id or 0) * 7 % 900),
                "shade_group": "AB"[index % 5 == 4],
                "shade_band": "SB/%04d" % (10 + (roll.booking_line_id.id or 0) % 50),
                "shrinkage_group": "S1" if index % 4 else "S2",
                "width_cm": WIDTH_CM.get(code, 148.0) - (index % 3),
                "gsm": GSM.get(code, 200.0) + (index % 3) - 1,
                "roll_user_id": (self._ref(B + "user_vivek") or self.env.user).id,
            })
        return rolls

    def _next_roll_name(self):
        Lot = self.env["stock.lot"]
        number = 710
        last = Lot.search([("name", "=like", "R0____")], order="name desc", limit=1)
        if last and last.name[1:].isdigit():
            number = max(number, int(last.name[1:]) + 1)
        # names given to move lines of the picking being prepared are not lots yet
        pending = self.env["stock.move.line"].search([("lot_name", "=like", "R0____"), ("state", "!=", "done")])
        for name in pending.mapped("lot_name"):
            if name[1:].isdigit():
                number = max(number, int(name[1:]) + 1)
        return "R%05d" % number

    def _approve_all(self, rolls):
        for index, roll in enumerate(rolls.filtered(lambda r: r.roll_status == "received")):
            roll.points_per_100sqyd = (7.5, 12.5, 9.1, 14.0, 18.2, 22.6)[index % 6]
            roll.action_roll_approve()

    def _consume(self, rolls, keep=1, remnant=12.5):
        """Fabric already cut: empty every roll but the last ``keep`` ones, which keep a remnant."""
        location = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1).lot_stock_id
        Quant = self.env["stock.quant"].sudo()
        ordered = rolls.sorted("name")
        for index, roll in enumerate(ordered):
            on_hand = roll.product_qty
            left = remnant if index >= len(ordered) - keep else 0.0
            if on_hand > left:
                Quant._update_available_quantity(roll.product_id, location, -(on_hand - left), lot_id=roll)

    def _inspect(self, roll, defects, override=None, reason=None, finish=True, days=-20, yards=None):
        """``defects``: list of (defect code, band, yard)."""
        Insp = self.env["garment.fabric.inspection"]
        vivek = self._ref(B + "user_vivek") or self.env.user
        insp = Insp.create({"lot_id": roll.id, "inspector_id": vivek.id, "frame": "Frame 2",
                            "date_inspected": fields.Date.context_today(self) + timedelta(days=days),
                            "gsm_measured": roll.gsm})
        if yards:
            insp.inspected_length_yd = yards
        for code, band, yard in defects:
            defect = self._ref(B + "defect_" + code.lower())
            insp.tablet_add_defect(defect.id if defect else False, band, yard)
        if override:
            insp.write({"result_override": override, "reason": reason})
        if finish:
            insp.action_done()
        return insp

    @staticmethod
    def _spread(count, bands, length):
        """``count`` defects spread along ``length`` yards with the given band cycle."""
        codes = ["F02", "F01", "F05", "F04", "F08", "F03", "F06", "F07"]
        step = max(length / (count + 1), 1.0)
        return [(codes[i % len(codes)], bands[i % len(bands)], round(step * (i + 1), 1)) for i in range(count)]

    # ------------------------------------------------------------------
    @api.model
    def _load_demo(self):
        if self._ref(X + "booking_tee_late"):
            return True
        tee_late = self._ref(M + "order_tee_late")
        jean_late = self._ref(M + "order_jean_late")
        polo_run = self._ref(M + "order_polo_running")
        chino_run = self._ref(M + "order_chino_running")
        tee_conf = self._ref(M + "order_tee_confirmed")
        polo_done = self._ref(M + "order_polo_shipped")
        if not all((tee_late, jean_late, polo_run, chino_run, tee_conf, polo_done)):
            return True  # merchandising demo not loaded

        # Fabric used up by orders already cut: in house, approved, mostly issued to cutting.
        done_bookings = []
        for xmlid, order, days in (("booking_polo_shipped", polo_done, -110), ("booking_tee_late", tee_late, -75),
                                   ("booking_jean_late", jean_late, -70), ("booking_polo_running", polo_run, -55)):
            booking = self._booking(xmlid, order)
            rolls = self._receive(booking, received_days=days)
            self._approve_all(rolls)
            done_bookings.append((booking, rolls))
        # Screen 44 style inspections on a couple of rolls of the running polo order
        polo_rolls = done_bookings[3][1].sorted("name")
        self._consume(done_bookings[0][1], keep=0)
        self._consume(done_bookings[1][1], keep=2)
        self._consume(done_bookings[2][1], keep=1)
        self._consume(polo_rolls[:-3], keep=0)

        # Chino in its first week: fabric short (grey twill and pocketing still coming), date passed.
        chino = self._booking("booking_chino_running", chino_run, needed=-4)
        chino_rolls = self._receive(chino, share=0.82, received_days=-12)
        chino_rolls = chino_rolls.sorted("name")
        self._approve_all(chino_rolls[:-4])
        self._consume(chino_rolls[:-6], keep=1)
        hold_roll, reject_roll, shade_roll = chino_rolls[-4], chino_rolls[-3], chino_rolls[-2]
        # chino_rolls[-1] stays received (waiting for inspection)
        yd = hold_roll._roll_length_yards()
        self._inspect(hold_roll, self._spread(30, ["4", "3", "4", "2"], yd), days=-8)
        self._inspect(reject_roll, self._spread(36, ["4", "4", "3"], reject_roll._roll_length_yards()),
                      override="reject", reason="Holes and a crease line across the full width", days=-7)
        self._inspect(shade_roll, self._spread(9, ["2", "1", "3"], shade_roll._roll_length_yards()),
                      override="hold", reason="Shade differs from the approved band; waiting for the buyer's comment",
                      days=-6)
        for xmlid, roll in (("roll_held_points", hold_roll), ("roll_rejected", reject_roll),
                            ("roll_held_shade", shade_roll), ("roll_received_chino", chino_rolls[-1])):
            self._xmlid(roll, xmlid)

        # Passing inspections on rolls still on hand
        for days, roll in enumerate(polo_rolls[-3:]):
            self._inspect(roll, self._spread(6 + days, ["1", "2", "1", "3"], roll._roll_length_yards()),
                          days=-30 + days)

        # Second tee order: ordered, first rolls arrived last days, one on the tablet now.
        tee2 = self._booking("booking_tee_confirmed", tee_conf)
        tee2_rolls = self._receive(tee2, share=0.25, received_days=-2,
                                   only=tee2.line_ids.filtered(lambda l: l.colour_id == self._ref(B + "colour_navy")))
        tee2_rolls = tee2_rolls.sorted("name")
        if tee2_rolls:
            insp = self._inspect(tee2_rolls[0], self._spread(5, ["1", "2"], 46.5), finish=False, days=0)
            insp.current_yard = 46.5
            self._xmlid(insp, "inspection_on_tablet")

        # Trims: chino trims short (labels and buttons still coming), polo trims still a draft booking.
        trims = self._booking("booking_chino_trims", chino_run, booking_of="trims", needed=-7)
        if trims.line_ids:
            self._receive(trims, share=0.6, received_days=-10)
        self._booking("booking_tee_trims", tee_conf, booking_of="trims", confirm=False)
        return True
