from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _garment_portal_kind(self):
        """'buyer', 'vendor' or False for the commercial partner of a portal user."""
        partner = self.commercial_partner_id
        if partner.is_jobwork_vendor and not partner.is_garment_buyer:
            return "vendor"
        if partner.is_garment_buyer:
            return "buyer"
        return False
