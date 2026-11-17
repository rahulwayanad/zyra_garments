from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

METRE_PER_YARD = 0.9144
ROLL_BOARD_ORDER = ["approved", "hold", "received", "rejected"]


class StockLot(models.Model):
    """Materials adds the receipt, booking, relaxation and inspection side of a fabric roll."""

    _inherit = "stock.lot"

    booking_line_id = fields.Many2one("garment.fabric.booking.line", string="Booking Line", index=True,
                                      copy=False, ondelete="set null")
    fabric_booking_id = fields.Many2one("garment.fabric.booking", string="Fabric Booking", index=True,
                                        related="booking_line_id.booking_id", store=True)
    garment_order_id = fields.Many2one("garment.order", string="Received For Order", index=True,
                                       related="booking_line_id.booking_id.order_id", store=True)
    roll_colour_id = fields.Many2one(related="booking_line_id.colour_id", string="Colourway")
    roll_colour_label = fields.Char(string="Colour", compute="_compute_roll_colour")
    roll_colour_hex = fields.Char(string="Swatch", compute="_compute_roll_colour")

    roll_received_qty = fields.Float(string="Received Length", digits=(16, 2), tracking=True,
                                     help="Length (or weight) received, in the fabric's unit.")
    roll_received_date = fields.Date(string="Roll Received On")
    roll_promised_date = fields.Date(string="Roll Promised On")
    roll_delivered_on_time = fields.Boolean(string="Delivered On Time", compute="_compute_on_time")
    roll_supplier_id = fields.Many2one("res.partner", string="Fabric Supplier")
    roll_owner_id = fields.Many2one("res.partner", string="Owned By",
                                    help="Buyer that owns the fabric (CMT); empty = our own fabric.")
    roll_user_id = fields.Many2one("res.users", string="Received By", default=lambda self: self.env.user)
    shade_band = fields.Char(string="Shade Band", tracking=True)
    width_in = fields.Float(string="Measured Width (in)", digits=(16, 2), compute="_compute_width_in",
                            inverse="_inverse_width_in")

    roll_inspection_ids = fields.One2many("garment.fabric.inspection", "lot_id", string="Inspections")
    roll_inspection_count = fields.Integer(string="Inspection Count", compute="_compute_inspection")
    roll_inspected_date = fields.Date(string="Roll Inspected On", compute="_compute_inspection")

    relax_start = fields.Datetime(string="Relaxation Started", copy=False)
    relax_until = fields.Datetime(string="Relaxed At", copy=False)
    relaxation_status = fields.Selection([
        ("free", "Free"), ("relaxing", "Relaxing"), ("relaxed", "Relaxed"),
    ], string="Relaxation", compute="_compute_relaxation",
        help="Free: no relaxation started. Relaxing: unrolled and resting until the time shown. Relaxed: ready.")

    roll_over_limit = fields.Boolean(string="Over Accept Limit", compute="_compute_roll_over_limit")

    @api.depends("points_per_100sqyd", "company_id")
    def _compute_roll_over_limit(self):
        for lot in self:
            limit = (lot.company_id or self.env.company).garment_fabric_accept_points
            lot.roll_over_limit = lot.points_per_100sqyd > limit

    @api.model
    def _group_expand_roll_status(self, values, domain):
        # Roll board column order (screen 41): approved, on hold, received, rejected.
        return list(ROLL_BOARD_ORDER)

    @api.depends("booking_line_id.colour_id", "product_id")
    def _compute_roll_colour(self):
        for lot in self:
            colour = lot.booking_line_id.colour_id or lot.product_id.garment_colour_id
            lot.roll_colour_label = colour.name or ""
            lot.roll_colour_hex = colour.hex or "#c9c4dd"

    @api.depends("roll_received_date", "roll_promised_date")
    def _compute_on_time(self):
        for lot in self:
            lot.roll_delivered_on_time = bool(lot.roll_received_date and lot.roll_promised_date
                                              and lot.roll_received_date <= lot.roll_promised_date)

    @api.depends("width_cm")
    def _compute_width_in(self):
        for lot in self:
            lot.width_in = lot.width_cm / 2.54 if lot.width_cm else 0.0

    def _inverse_width_in(self):
        for lot in self:
            lot.width_cm = lot.width_in * 2.54

    def _compute_inspection(self):
        for lot in self:
            done = lot.roll_inspection_ids.filtered(lambda i: i.state == "done")
            lot.roll_inspection_count = len(lot.roll_inspection_ids)
            lot.roll_inspected_date = max(done.mapped("date_inspected")) if done else False

    @api.depends("relax_start", "relax_until")
    def _compute_relaxation(self):
        now = fields.Datetime.now()
        for lot in self:
            if not lot.relax_start:
                lot.relaxation_status = "free"
            elif lot.relax_until and lot.relax_until > now:
                lot.relaxation_status = "relaxing"
            else:
                lot.relaxation_status = "relaxed"

    def _roll_length_yards(self):
        """Received length in yards (rolls are received in metres; 1 yd = 0.9144 m)."""
        self.ensure_one()
        if not self.roll_received_qty:
            return 0.0
        metre = self.env.ref("uom.product_uom_meter", raise_if_not_found=False)
        uom = self.product_id.uom_id
        if metre and uom and uom.category_id == metre.category_id:
            return round(uom._compute_quantity(self.roll_received_qty, metre, round=False) / METRE_PER_YARD, 2)
        return 0.0

    @api.model_create_multi
    def create(self, vals_list):
        lots = super().create(vals_list)
        bookings = lots.sudo().mapped("fabric_booking_id")
        if bookings:
            bookings._sync_state()
        return lots

    def write(self, vals):
        res = super().write(vals)
        if {"roll_status", "roll_received_qty", "booking_line_id"} & set(vals):
            bookings = self.sudo().mapped("fabric_booking_id")
            if bookings:
                bookings._sync_state()
        return res

    # ------------------------------------------------------------------
    # Buttons (screen 42)
    # ------------------------------------------------------------------
    def action_inspect_again(self):
        self.ensure_one()
        self._check_is_roll()
        inspection = self.env["garment.fabric.inspection"].create({"lot_id": self.id})
        return inspection.action_open_tablet()

    def action_start_relaxation(self):
        hours = self.env.company.garment_relax_hours or 0
        now = fields.Datetime.now()
        for lot in self:
            lot._check_is_roll()
            lot.write({"relax_start": now, "relax_until": now + timedelta(hours=hours)})
            lot.message_post(body=_("Relaxation started; ready at %s.", fields.Datetime.to_string(lot.relax_until)))
        return True

    def action_print_roll_label(self):
        return self.env.ref("zyra_garment_materials.action_report_roll_label").report_action(self)

    def action_view_roll_inspections(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "zyra_garment_materials.action_garment_fabric_inspection")
        action["domain"] = [("lot_id", "=", self.id)]
        action["context"] = {"default_lot_id": self.id}
        return action


class ResCompany(models.Model):
    _inherit = "res.company"

    garment_relax_hours = fields.Integer(string="Fabric Relaxation (hours)", default=24,
                                         help="How long an unrolled roll rests before it can be laid.")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    garment_relax_hours = fields.Integer(related="company_id.garment_relax_hours", readonly=False)

