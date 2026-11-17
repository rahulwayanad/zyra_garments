from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    garment_aql_major = fields.Float(string="AQL major", default=2.5, digits=(16, 2),
                                     help="AQL used for major defects on final inspections.")
    garment_aql_minor = fields.Float(string="AQL minor", default=4.0, digits=(16, 2),
                                     help="AQL used for minor defects on final inspections.")
    garment_dhu_limit = fields.Float(string="DHU limit (%)", default=5.0,
                                     help="End-line DHU above this is shown in red on the tablet.")
    garment_capa_threshold = fields.Integer(string="CAPA after (occurrences)", default=10,
                                            help="Raise a corrective action when the same defect at the same "
                                                 "place is recorded this many times on one line within the window.")
    garment_capa_window_days = fields.Integer(string="CAPA window (days)", default=3)

    @api.constrains("garment_capa_threshold", "garment_capa_window_days", "garment_dhu_limit")
    def _check_garment_quality_figures(self):
        for company in self:
            if company.garment_capa_threshold < 1 or company.garment_capa_window_days < 1:
                raise ValidationError(self.env._("The CAPA threshold and window must be at least 1."))
            if company.garment_dhu_limit < 0:
                raise ValidationError(self.env._("The DHU limit cannot be negative."))


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    garment_aql_major = fields.Float(related="company_id.garment_aql_major", readonly=False)
    garment_aql_minor = fields.Float(related="company_id.garment_aql_minor", readonly=False)
    garment_dhu_limit = fields.Float(related="company_id.garment_dhu_limit", readonly=False)
    garment_capa_threshold = fields.Integer(related="company_id.garment_capa_threshold", readonly=False)
    garment_capa_window_days = fields.Integer(related="company_id.garment_capa_window_days", readonly=False)
