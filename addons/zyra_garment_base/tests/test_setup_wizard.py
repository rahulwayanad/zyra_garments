from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestGarmentSetupWizard(TransactionCase):

    def _wizard(self, **vals):
        return self.env["garment.setup.wizard"].create(vals)

    def test_wizard_opens_with_company_figures(self):
        self.env.company.write({"working_minutes_per_day": 450, "target_efficiency": 60.0})
        wizard = self._wizard()
        self.assertEqual(wizard.working_minutes_per_day, 450)
        self.assertEqual(wizard.target_efficiency, 60.0)

    def test_wizard_writes_company_figures_and_business_models(self):
        wizard = self._wizard(working_minutes_per_day=500, target_efficiency=68.0, week_start="7",
                              minute_value=0.2, margin_floor_pct=10.0, model_own_brand=True,
                              model_cmt=False)
        wizard.action_save_setup()
        company = self.env.company
        self.assertEqual(company.working_minutes_per_day, 500)
        self.assertEqual(company.target_efficiency, 68.0)
        self.assertEqual(company.garment_week_start, "7")
        self.assertAlmostEqual(company.minute_value, 0.2)
        self.assertEqual(company.margin_floor_pct, 10.0)
        self.assertTrue(company.garment_model_own_brand)
        self.assertFalse(company.garment_model_cmt)

    def test_wizard_creates_size_ranges_from_presets_in_order(self):
        self._wizard(preset_s_xl=True, preset_xs_xxl=True, preset_kids_2_14=True).action_save_setup()
        s_xl = self.env.ref("zyra_garment_base.size_range_s_xl")
        self.assertEqual(s_xl.size_ids.sorted("sequence").mapped("name"), ["S", "M", "L", "XL"])
        xs_xxl = self.env.ref("zyra_garment_base.size_range_xs_xxl")
        self.assertEqual(xs_xxl.size_ids.sorted("sequence").mapped("name"), ["XS", "S", "M", "L", "XL", "XXL"])
        kids = self.env.ref("zyra_garment_base.size_range_kids_2_14")
        self.assertEqual(kids.size_count, 7)
        self.assertEqual(self.env.ref("zyra_garment_base.size_s_xl_m").range_id, s_xl)

    def test_wizard_loads_libraries_only_once(self):
        vals = dict(preset_s_xl=True, preset_xs_xxl=True, preset_kids_2_14=True,
                    load_pom_library=True, load_defect_library=True)
        self._wizard(**vals).action_save_setup()
        counts = (
            self.env["garment.pom"].search_count([]),
            self.env["garment.defect"].search_count([]),
            self.env["garment.size.range"].search_count([]),
            self.env["garment.size"].search_count([]),
        )
        self.assertGreaterEqual(counts[0], 30)
        self.assertGreaterEqual(counts[1], 40)
        self._wizard(**vals).action_save_setup()
        self.assertEqual(counts, (
            self.env["garment.pom"].search_count([]),
            self.env["garment.defect"].search_count([]),
            self.env["garment.size.range"].search_count([]),
            self.env["garment.size"].search_count([]),
        ))
        self.assertEqual(self.env.ref("zyra_garment_base.pom_t01").name, "Chest 1/2")
        self.assertEqual(self.env.ref("zyra_garment_base.defect_w01").severity, "major")

    def test_library_does_not_duplicate_a_code_entered_by_hand(self):
        pom = self.env["garment.pom"].search([("code", "=", "B08")])
        if not pom:
            pom = self.env["garment.pom"].create({"code": "B08", "name": "Inside leg (own)"})
        self.env["garment.library"]._load_pom_library()
        self.assertEqual(self.env["garment.pom"].search_count([("code", "=", "B08")]), 1)

    def test_wizard_assigns_users_to_roles(self):
        user = self.env["res.users"].create({"name": "New Cutter", "login": "zyra_test_cutter"})
        wizard = self._wizard(role_line_ids=[(0, 0, {"user_id": user.id, "role": "cutting"})])
        wizard.action_save_setup()
        self.assertTrue(user.has_group("zyra_garment_base.group_garment_cutting"))

    def test_wizard_proposes_existing_role_holders(self):
        user = self.env["res.users"].create({
            "name": "Existing QC", "login": "zyra_test_existing_qc",
            "groups_id": [(6, 0, [self.env.ref("zyra_garment_base.group_garment_quality").id])],
        })
        wizard = self._wizard()
        line = wizard.role_line_ids.filtered(lambda l: l.user_id == user)
        self.assertEqual(line.role, "quality")

    def test_unticked_area_hides_its_section_menu(self):
        menu = self.env.ref("zyra_garment_base.menu_garment_wages")
        self._wizard(area_wages=False).action_save_setup()
        self.assertFalse(menu.active)
        self.assertFalse(self.env.company.garment_area_wages)
        self._wizard(area_wages=True).action_save_setup()
        self.assertTrue(menu.active)

    def test_only_garment_admin_can_save_setup(self):
        user = self.env["res.users"].create({
            "name": "Plain Manager", "login": "zyra_test_plain_fm",
            "groups_id": [(6, 0, [self.env.ref("zyra_garment_base.group_garment_factory_manager").id])],
        })
        wizard = self._wizard()
        with self.assertRaises(AccessError):
            wizard.with_user(user).action_save_setup()
