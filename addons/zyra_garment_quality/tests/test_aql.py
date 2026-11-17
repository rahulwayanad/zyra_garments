from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import QualityCase


@tagged("post_install", "-at_install", "zyra")
class TestAql(QualityCase):

    def lookup(self, lot, aql):
        return self.env["garment.aql.limit"]._garment_lookup(lot, aql)

    def test_aql_lot_1200_is_letter_j_and_1201_is_letter_k(self):
        self.assertEqual(self.lookup(1200, 2.5), {"code_letter": "J", "sample_size": 80, "accept": 5, "reject": 6})
        self.assertEqual(self.lookup(1201, 2.5), {"code_letter": "K", "sample_size": 125, "accept": 7, "reject": 8})
        self.assertEqual(self.lookup(1200, 4.0)["accept"], 7)
        self.assertEqual(self.lookup(1201, 4.0), {"code_letter": "K", "sample_size": 125, "accept": 10, "reject": 11})

    def test_aql_boundaries_of_letters_h_j_l(self):
        self.assertEqual(self.lookup(500, 2.5)["code_letter"], "H")
        self.assertEqual(self.lookup(500, 2.5)["sample_size"], 50)
        self.assertEqual(self.lookup(501, 2.5)["code_letter"], "J")
        self.assertEqual(self.lookup(3200, 2.5)["code_letter"], "K")
        self.assertEqual(self.lookup(3201, 2.5), {"code_letter": "L", "sample_size": 200, "accept": 10, "reject": 11})
        self.assertEqual(self.lookup(3201, 4.0)["accept"], 14)

    def test_aql_arrow_rows_use_the_plan_the_arrow_points_to(self):
        # Letter D (lot 26-50) at AQL 2.5 points up to C: 5 pieces, accept 0.
        self.assertEqual(self.lookup(50, 2.5), {"code_letter": "D", "sample_size": 5, "accept": 0, "reject": 1})
        # Letter E (lot 51-90) at AQL 2.5 points down to F: 20 pieces, accept 1.
        self.assertEqual(self.lookup(51, 2.5)["sample_size"], 20)
        # Biggest lots stop at the last plan of the column.
        self.assertEqual(self.lookup(600000, 2.5)["accept"], 21)

    def test_final_sample_is_the_larger_plan_and_never_more_than_the_lot(self):
        insp = self.inspect(lot=1633)
        self.assertEqual((insp.code_letter, insp.sample_size), ("K", 125))
        self.assertEqual((insp.major_accept, insp.major_reject, insp.minor_accept, insp.minor_reject), (7, 8, 10, 11))
        # Letter E: major plan 20 pieces, minor plan 13 pieces -> 20.
        self.assertEqual(self.inspect(lot=60).sample_size, 20)
        # Lot of 3 at AQL 2.5 asks 5 pieces: capped to the lot (100 % check).
        self.assertEqual(self.inspect(lot=3).sample_size, 3)

    def test_aql_tables_are_editable_data(self):
        row = self.env.ref("zyra_garment_quality.aql_limit_2_5_k")
        row.write({"accept": 6, "reject": 7})
        self.assertEqual(self.inspect(lot=1633).major_accept, 6)

    def test_aql_lookup_without_lot_or_row_raises(self):
        with self.assertRaises(UserError):
            self.lookup(0, 2.5)
        with self.assertRaises(UserError):
            self.lookup(1000, 0.65)
        insp = self.inspect(lot=1000, aql_major=0.65)
        self.assertTrue(insp.plan_error)
        with self.assertRaises(UserError):
            insp.action_complete()
