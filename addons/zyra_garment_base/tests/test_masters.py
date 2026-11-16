from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "zyra")
class TestGarmentMasters(TransactionCase):

    def test_sizes_follow_their_sequence_not_their_name(self):
        size_range = self.env["garment.size.range"].create({
            "name": "Test 28-32",
            "size_ids": [(0, 0, {"name": "32", "sequence": 3}), (0, 0, {"name": "28", "sequence": 1}),
                         (0, 0, {"name": "30", "sequence": 2})],
        })
        sizes = self.env["garment.size"].search([("range_id", "=", size_range.id)])
        self.assertEqual(sizes.mapped("name"), ["28", "30", "32"])
        self.assertEqual(size_range.size_names, "28 · 30 · 32")

    def test_colour_hex_must_be_a_six_digit_code(self):
        with self.assertRaises(ValidationError):
            self.env["garment.colour"].create({"name": "Bad", "hex": "blue"})
        colour = self.env["garment.colour"].create({"name": "Good", "hex": "#1F2A44"})
        self.assertEqual(colour.hex, "#1F2A44")

    @mute_logger("odoo.sql_db")
    def test_defect_codes_are_unique(self):
        self.env["garment.defect"].create({"code": "ZZ1", "name": "One"})
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.env["garment.defect"].create({"code": "ZZ1", "name": "Two"})

    def test_operation_library_covers_tshirt_and_jean(self):
        tee = self.env.ref("zyra_garment_base.garment_type_tshirt")
        jean = self.env.ref("zyra_garment_base.garment_type_jean")
        Operation = self.env["garment.operation"]
        self.assertGreaterEqual(Operation.search_count([("type_id", "=", tee.id)]), 10)
        self.assertGreaterEqual(Operation.search_count([("type_id", "=", jean.id)]), 20)
        self.assertTrue(self.env.ref("zyra_garment_base.operation_tee_01").machine_type_id)

    def test_display_name_shows_code(self):
        pom = self.env["garment.pom"].create({"code": "ZP1", "name": "Test point"})
        self.assertEqual(pom.display_name, "[ZP1] Test point")
