from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError

from ..models.res_company import WEEK_DAYS

# Role selection key -> group xml id (labels follow screen 119)
ROLES = [
    ("merchandiser", "Merchandiser"),
    ("techpack_designer", "Tech pack designer"),
    ("costing", "Costing"),
    ("fabric_store", "Fabric & trims store"),
    ("cutting", "Cutting"),
    ("line_supervisor", "Line supervisor / IE"),
    ("quality", "Quality controller"),
    ("packing_shipping", "Packing & shipping"),
    ("wages", "Wages"),
    ("factory_manager", "Factory manager"),
    ("admin", "Garment admin"),
]


def role_group_xmlid(role):
    return f"zyra_garment_base.group_garment_{role}"


# Area field on the wizard / company -> section menu it shows or hides (None: no menu of its own)
AREA_MENUS = {
    "area_merch": "zyra_garment_base.menu_garment_merch",
    "area_materials": "zyra_garment_base.menu_garment_materials",
    "area_cutting": "zyra_garment_base.menu_garment_cutting",
    "area_sewing": "zyra_garment_base.menu_garment_sewing",
    "area_jobwork": "zyra_garment_jobwork.menu_garment_jobwork",  # soft: owned by jobwork
    "area_quality": "zyra_garment_base.menu_garment_quality",
    "area_shipping": "zyra_garment_base.menu_garment_shipping",
    "area_wages": "zyra_garment_base.menu_garment_wages",
    "area_compliance": None,
}

COMPANY_FIGURES = [
    "working_minutes_per_day", "target_efficiency", "minute_value", "margin_floor_pct",
]
COMPANY_GARMENT_FIELDS = [
    "week_start", "fabric_accept_points",
    "model_fob", "model_cmt", "model_own_brand", "model_mtm", "model_decoration",
] + list(AREA_MENUS)


class GarmentSetupWizard(models.TransientModel):
    _name = "garment.setup.wizard"
    _description = "Garment Factory Setup"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")

    # Business models you run
    model_fob = fields.Boolean(string="FOB / full package")
    model_cmt = fields.Boolean(string="CMT (buyer supplies fabric)")
    model_own_brand = fields.Boolean(string="Own brand stock")
    model_mtm = fields.Boolean(string="Made to measure")
    model_decoration = fields.Boolean(string="Decorated and personalised team wear")

    # Areas in the menu
    area_merch = fields.Boolean(string="Merchandising")
    area_materials = fields.Boolean(string="Materials")
    area_cutting = fields.Boolean(string="Cutting")
    area_sewing = fields.Boolean(string="Sewing floor")
    area_jobwork = fields.Boolean(string="Job work")
    area_quality = fields.Boolean(string="Quality")
    area_shipping = fields.Boolean(string="Packing and shipping")
    area_wages = fields.Boolean(string="Wages")
    area_compliance = fields.Boolean(string="Compliance")

    # Working time and company figures
    working_minutes_per_day = fields.Integer(string="Working minutes per day")
    target_efficiency = fields.Float(string="Target line efficiency (%)")
    week_start = fields.Selection(WEEK_DAYS, string="Week starts on")
    minute_value = fields.Monetary(string="Value of a standard minute", currency_field="currency_id")
    margin_floor_pct = fields.Float(string="Margin floor (%)")
    fabric_accept_points = fields.Float(string="Fabric accept limit (pts / 100 sq yd)")

    # Size ranges and libraries
    preset_s_xl = fields.Boolean(string="S-XL")
    preset_xs_xxl = fields.Boolean(string="XS-XXL")
    preset_kids_2_14 = fields.Boolean(string="Kids 2-14")
    load_pom_library = fields.Boolean(string="Points of measure library", default=True)
    load_defect_library = fields.Boolean(string="Defect library", default=True)
    pom_count = fields.Integer(compute="_compute_library_counts")
    defect_count = fields.Integer(compute="_compute_library_counts")

    # Roles
    role_line_ids = fields.One2many("garment.setup.wizard.role", "wizard_id", string="Roles")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env["res.company"].browse(res.get("company_id")) or self.env.company
        for name in COMPANY_FIGURES:
            res.setdefault(name, company[name])
        for name in COMPANY_GARMENT_FIELDS:
            res.setdefault(name, company[f"garment_{name}"])
        library = self.env["garment.library"]
        for preset in ("s_xl", "xs_xxl", "kids_2_14"):
            res.setdefault(f"preset_{preset}", not library._xmlid_record(f"size_range_{preset}")
                           and preset != "kids_2_14")
        if "role_line_ids" in fields_list and "role_line_ids" not in res:
            res["role_line_ids"] = [Command.create(vals) for vals in self._default_role_lines()]
        return res

    @api.model
    def _default_role_lines(self):
        """One line per internal user who already holds a garment role (their main role)."""
        lines = []
        root = self.env.ref("base.user_root")
        users = self.env["res.users"].search([("share", "=", False), ("id", "!=", root.id)], order="id")
        for user in users:
            # main role = the most senior one held (Factory Manager and Admin imply the others)
            for role, _label in reversed(ROLES):
                group = self.env.ref(role_group_xmlid(role))
                if group in user.groups_id:
                    lines.append({"user_id": user.id, "role": role})
                    break
        return lines

    def _compute_library_counts(self):
        poms = self.env["garment.pom"].with_context(active_test=False).search_count([])
        defects = self.env["garment.defect"].with_context(active_test=False).search_count([])
        for wizard in self:
            wizard.pom_count = poms
            wizard.defect_count = defects

    def _check_setup_rights(self):
        if not self.env.user.has_group("zyra_garment_base.group_garment_admin"):
            raise AccessError(_("Only a Garment Admin can run the factory setup."))

    def _apply_company(self):
        company = self.company_id.sudo()
        vals = {name: self[name] for name in COMPANY_FIGURES}
        vals.update({f"garment_{name}": self[name] for name in COMPANY_GARMENT_FIELDS})
        company.write(vals)

    def _apply_menus(self):
        for area, menu_xmlid in AREA_MENUS.items():
            menu = menu_xmlid and self.env.ref(menu_xmlid, raise_if_not_found=False)
            if menu and menu.sudo().active != self[area]:
                menu.sudo().active = self[area]

    def _apply_libraries(self):
        library = self.env["garment.library"]
        for preset in ("s_xl", "xs_xxl", "kids_2_14"):
            if self[f"preset_{preset}"]:
                library._load_size_preset(preset)
        if self.load_pom_library:
            library._load_pom_library()
        if self.load_defect_library:
            library._load_defect_library()

    def _apply_roles(self):
        for line in self.role_line_ids.filtered("user_id"):
            group = self.env.ref(role_group_xmlid(line.role))
            if group not in line.user_id.groups_id:
                line.user_id.sudo().write({"groups_id": [Command.link(group.id)]})

    def action_save_setup(self):
        """Save setup: company figures, menu areas, size ranges, libraries, roles."""
        self.ensure_one()
        self._check_setup_rights()
        self._apply_company()
        self._apply_libraries()
        self._apply_roles()
        self._apply_menus()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Factory setup saved"),
                "message": _("Company figures, size ranges, libraries and roles are up to date."),
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }


class GarmentSetupWizardRole(models.TransientModel):
    _name = "garment.setup.wizard.role"
    _description = "Garment Factory Setup: Role"
    _order = "id"

    wizard_id = fields.Many2one("garment.setup.wizard", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", string="User", required=True,
                              domain=[("share", "=", False)])
    role = fields.Selection(ROLES, required=True, default="merchandiser")
