from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ROLL_STATUSES = [
    ("received", "Received"),
    ("approved", "Approved"),
    ("hold", "Hold"),
    ("rejected", "Rejected"),
]


class StockLot(models.Model):
    """A fabric roll is a stock.lot with ``is_fabric_roll`` set."""

    _inherit = "stock.lot"

    is_fabric_roll = fields.Boolean(string="Fabric Roll", index=True)
    roll_status = fields.Selection(
        ROLL_STATUSES, string="Roll Status", default="received", tracking=True, index=True,
        group_expand="_group_expand_roll_status")
    roll_hold_reason = fields.Char(string="Hold / Reject Reason", tracking=True)
    dye_lot = fields.Char(string="Dye Lot", tracking=True)
    shade_group = fields.Char(string="Shade Group", tracking=True,
                              help="Rolls of one shade group can be laid together.")
    shrinkage_group = fields.Char(string="Shrinkage Group", tracking=True)
    width_cm = fields.Float(string="Width (cm)", digits=(16, 1))
    gsm = fields.Float(string="GSM", digits=(16, 1), help="Fabric weight in grams per square metre.")
    points_per_100sqyd = fields.Float(
        string="Points / 100 sq yd", digits=(16, 1),
        help="4-point inspection score, written by the fabric inspection.")

    @api.model
    def _group_expand_roll_status(self, values, domain):
        return [key for key, _label in ROLL_STATUSES]

    @api.constrains("width_cm", "gsm", "points_per_100sqyd")
    def _check_roll_measures(self):
        for lot in self:
            if lot.width_cm < 0 or lot.gsm < 0 or lot.points_per_100sqyd < 0:
                raise ValidationError(_("Width, GSM and inspection points of roll %s cannot be negative.",
                                        lot.name))

    # ------------------------------------------------------------------
    # Roll status changes
    # ------------------------------------------------------------------
    def _check_is_roll(self):
        not_rolls = self.filtered(lambda lot: not lot.is_fabric_roll)
        if not_rolls:
            raise UserError(_("Lot %s is not a fabric roll.", ", ".join(not_rolls.mapped("name"))))

    def action_roll_approve(self):
        """Received or held rolls can be approved; a rejected roll must be reset first."""
        self._check_is_roll()
        rejected = self.filtered(lambda lot: lot.roll_status == "rejected")
        if rejected:
            raise UserError(_(
                "Roll %s is rejected. A Factory Manager must reset it to Received before it can be approved.",
                ", ".join(rejected.mapped("name"))))
        self.write({"roll_status": "approved", "roll_hold_reason": False})
        return True

    def action_roll_hold(self, reason=None):
        """Put rolls on hold; a rejected roll cannot be put on hold."""
        self._check_is_roll()
        rejected = self.filtered(lambda lot: lot.roll_status == "rejected")
        if rejected:
            raise UserError(_("Roll %s is already rejected.", ", ".join(rejected.mapped("name"))))
        vals = {"roll_status": "hold"}
        if reason:
            vals["roll_hold_reason"] = reason
        self.write(vals)
        return True

    def action_roll_reject(self, reason=None):
        self._check_is_roll()
        vals = {"roll_status": "rejected"}
        if reason:
            vals["roll_hold_reason"] = reason
        self.write(vals)
        return True

    def action_roll_reset(self):
        """Back to Received. Releasing a rejected roll is a Factory Manager decision."""
        self._check_is_roll()
        if any(lot.roll_status == "rejected" for lot in self) and not self.env.user.has_group(
                "zyra_garment_base.group_garment_factory_manager"):
            raise UserError(_("Only a Factory Manager can release a rejected roll."))
        self.write({"roll_status": "received", "roll_hold_reason": False})
        return True
