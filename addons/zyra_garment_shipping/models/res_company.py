from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Clearly fake: 9999999 is not a GS1 allocation. Each factory enters its own GS1 company prefix.
DEMO_GS1_PREFIX = "9999999"


def gs1_check_digit(digits):
    """GS1 mod-10 check digit of a string of digits (weights 3, 1, 3, … from the right)."""
    if not digits or not digits.isdigit():
        raise ValueError("GS1 check digit needs digits only: %r" % (digits,))
    total = sum(int(ch) * (3 if i % 2 == 0 else 1) for i, ch in enumerate(reversed(digits)))
    return (10 - total % 10) % 10


class ResCompany(models.Model):
    _inherit = "res.company"

    garment_gs1_prefix = fields.Char(
        string="GS1 Company Prefix", default=DEMO_GS1_PREFIX,
        help="Company prefix allocated by GS1 (7 to 10 digits). The default 9999999 is a demo value only.")
    garment_sscc_extension = fields.Char(
        string="SSCC Extension Digit", default="0", size=1,
        help="First digit of the SSCC (0-9), free for the factory to use.")

    @api.constrains("garment_gs1_prefix", "garment_sscc_extension")
    def _check_garment_gs1(self):
        for company in self:
            prefix = company.garment_gs1_prefix or ""
            if prefix and (not prefix.isdigit() or not 7 <= len(prefix) <= 10):
                raise ValidationError(_("The GS1 company prefix must be 7 to 10 digits."))
            ext = company.garment_sscc_extension or ""
            if ext and (not ext.isdigit() or len(ext) != 1):
                raise ValidationError(_("The SSCC extension must be one digit (0-9)."))

    def _garment_make_sscc(self, serial):
        """SSCC-18 = extension (1) + company prefix + serial reference, padded to 17 digits, + check digit."""
        self.ensure_one()
        prefix = self.garment_gs1_prefix or DEMO_GS1_PREFIX
        ext = self.garment_sscc_extension or "0"
        serial = str(serial)
        room = 16 - len(prefix)
        if not serial.isdigit() or len(serial) > room:
            raise ValidationError(_("SSCC serial %(serial)s does not fit in %(room)s digits after the GS1 prefix.",
                                    serial=serial, room=room))
        body = ext + prefix + serial.zfill(room)
        return body + str(gs1_check_digit(body))


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    garment_gs1_prefix = fields.Char(related="company_id.garment_gs1_prefix", readonly=False)
    garment_sscc_extension = fields.Char(related="company_id.garment_sscc_extension", readonly=False)
