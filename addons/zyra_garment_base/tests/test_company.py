from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestGarmentCompany(TransactionCase):

    def test_new_company_gets_garment_defaults(self):
        company = self.env["res.company"].create({"name": "Zyra Test Unit 2"})
        self.assertEqual(company.target_efficiency, 65.0)
        self.assertEqual(company.working_minutes_per_day, 480)
        self.assertEqual(company.margin_floor_pct, 12.0)
        self.assertAlmostEqual(company.minute_value, 0.10)
        self.assertEqual(company.garment_fabric_accept_points, 40.0)
        self.assertEqual(company.garment_week_start, "1")
        self.assertTrue(company.garment_model_fob)
        self.assertFalse(company.garment_area_compliance)

    def test_settings_write_company_figures(self):
        settings = self.env["res.config.settings"].create({
            "minute_value": 0.15,
            "target_efficiency": 70.0,
            "working_minutes_per_day": 510,
            "margin_floor_pct": 15.0,
            "garment_fabric_accept_points": 35.0,
        })
        settings.execute()
        company = self.env.company
        self.assertAlmostEqual(company.minute_value, 0.15)
        self.assertEqual(company.target_efficiency, 70.0)
        self.assertEqual(company.working_minutes_per_day, 510)
        self.assertEqual(company.margin_floor_pct, 15.0)
        self.assertEqual(company.garment_fabric_accept_points, 35.0)

    def test_making_cost_is_sam_times_minute_value_over_efficiency(self):
        company = self.env.company
        company.write({"minute_value": 0.10, "target_efficiency": 50.0})
        self.assertAlmostEqual(company._garment_making_cost(12.0), 2.40)
