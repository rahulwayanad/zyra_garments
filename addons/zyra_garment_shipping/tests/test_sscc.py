from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.zyra_garment_shipping.models.res_company import gs1_check_digit

from .common import ShippingCase


@tagged("post_install", "-at_install", "zyra")
class TestSscc(ShippingCase):

    def test_gs1_check_digit_matches_the_published_gs1_example(self):
        # GS1 General Specifications example SSCC (00) 1 0614141 123456789 7
        self.assertEqual(gs1_check_digit("10614141123456789"), 7)
        self.assertEqual(gs1_check_digit("00000000000000000"), 0)
        self.assertEqual(gs1_check_digit("3"), 1)  # 3 × 3 = 9 → 1

    def test_sscc_is_18_digits_extension_prefix_serial_and_check_digit(self):
        company = self.env.company
        company.write({"garment_gs1_prefix": "1234567", "garment_sscc_extension": "3"})
        sscc = company._garment_make_sscc(42)
        self.assertEqual(len(sscc), 18)
        self.assertTrue(sscc.startswith("31234567"))
        self.assertEqual(sscc[8:17], "000000042")
        self.assertEqual(int(sscc[-1]), gs1_check_digit(sscc[:17]))

    def test_default_gs1_prefix_is_the_fake_demo_prefix(self):
        company = self.env["res.company"].create({"name": "Ship Test Co"})
        self.assertEqual(company.garment_gs1_prefix, "9999999")

    def test_gs1_prefix_must_be_7_to_10_digits(self):
        with self.assertRaises(ValidationError):
            self.env.company.garment_gs1_prefix = "12345"
        with self.assertRaises(ValidationError):
            self.env.company.garment_gs1_prefix = "12345AB"

    def test_serial_that_does_not_fit_after_the_prefix_is_refused(self):
        self.env.company.garment_gs1_prefix = "1234567890"
        with self.assertRaises(ValidationError):
            self.env.company._garment_make_sscc(10 ** 6)

    def test_packing_a_carton_gives_it_a_unique_valid_sscc(self):
        plan = self.make_plan(self.make_order())
        plan.action_generate_cartons()
        cartons = plan.carton_ids[:2]
        cartons.action_pack()
        a, b = cartons
        self.assertTrue(a.sscc and b.sscc)
        self.assertNotEqual(a.sscc, b.sscc)
        for c in cartons:
            self.assertEqual(int(c.sscc[-1]), gs1_check_digit(c.sscc[:17]))
            self.assertEqual(c.sscc_display, "(00) " + c.sscc)

    def test_scanned_sscc_with_application_identifier_finds_the_carton(self):
        plan = self.make_plan(self.make_order())
        plan.action_generate_cartons()
        plan.action_assign_sscc()
        carton = plan.carton_ids[3]
        wiz = self.env["garment.carton.pack.wizard"].create({"plan_id": plan.id, "scan": "(00) " + carton.sscc})
        wiz.action_pack()
        self.assertEqual(carton.state, "packed")
