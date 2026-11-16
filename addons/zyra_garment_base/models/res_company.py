from odoo import fields, models

WEEK_DAYS = [
    ("1", "Monday"),
    ("2", "Tuesday"),
    ("3", "Wednesday"),
    ("4", "Thursday"),
    ("5", "Friday"),
    ("6", "Saturday"),
    ("7", "Sunday"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    # --- Contract fields (kit prompt T1) -----------------------------------
    minute_value = fields.Monetary(
        string="Value of a Standard Minute",
        currency_field="currency_id",
        default=0.10,
        help="Cost of one standard minute of sewing in company currency. "
             "Making cost per piece = SAM x minute value / (target efficiency / 100).",
    )
    target_efficiency = fields.Float(
        string="Target Line Efficiency (%)",
        default=65.0,
        help="Percentage, e.g. 65.0 means 65 %.",
    )
    working_minutes_per_day = fields.Integer(string="Working Minutes per Day", default=480)
    margin_floor_pct = fields.Float(
        string="Margin Floor (%)",
        default=12.0,
        help="Cost sheets with a margin under this percentage need Factory Manager approval.",
    )

    # --- Extra company figures used by later waves ---------------------------
    garment_week_start = fields.Selection(WEEK_DAYS, string="Week Starts On", default="1")
    garment_fabric_accept_points = fields.Float(
        string="Fabric Accept Limit (points / 100 sq yd)",
        default=40.0,
        help="4-point inspection: rolls scoring above this limit go on hold.",
    )

    # Business models run by the factory (setup wizard, screen 119)
    garment_model_fob = fields.Boolean(string="FOB / full package", default=True)
    garment_model_cmt = fields.Boolean(string="CMT (buyer supplies fabric)", default=True)
    garment_model_own_brand = fields.Boolean(string="Own brand stock")
    garment_model_mtm = fields.Boolean(string="Made to measure")
    garment_model_decoration = fields.Boolean(string="Decorated and personalised team wear")

    # Areas shown in the Garment menu (setup wizard, screen 119)
    garment_area_merch = fields.Boolean(string="Merchandising", default=True)
    garment_area_materials = fields.Boolean(string="Materials", default=True)
    garment_area_cutting = fields.Boolean(string="Cutting", default=True)
    garment_area_sewing = fields.Boolean(string="Sewing floor", default=True)
    garment_area_jobwork = fields.Boolean(string="Job work", default=True)
    garment_area_quality = fields.Boolean(string="Quality", default=True)
    garment_area_shipping = fields.Boolean(string="Packing and shipping", default=True)
    garment_area_wages = fields.Boolean(string="Wages", default=True)
    garment_area_compliance = fields.Boolean(string="Compliance")

    def _garment_making_cost(self, sam):
        """Making cost per piece for ``sam`` minutes with this company's figures.

        Rule: making cost = SAM x minute value / target efficiency.
        """
        self.ensure_one()
        efficiency = (self.target_efficiency or 100.0) / 100.0
        return sam * self.minute_value / efficiency
