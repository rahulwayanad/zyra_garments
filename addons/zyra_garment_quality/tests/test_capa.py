from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import QualityCase


@tagged("post_install", "-at_install", "zyra")
class TestCapa(QualityCase):

    def capas(self):
        return self.env["garment.capa"].search([("defect_id", "=", self.d_major.id)])

    def test_capa_is_raised_when_same_defect_reaches_the_threshold(self):
        self.inspect(kind="endline", pieces=50, defects=[(self.d_major, 9, "left_sleeve")])
        self.assertFalse(self.capas(), "9 occurrences stay under the threshold of 10")
        self.inspect(kind="endline", pieces=50, defects=[(self.d_major, 1, "left_sleeve")])
        capa = self.capas()
        self.assertEqual(len(capa), 1)
        self.assertEqual(capa.occurrences, 10)
        self.assertTrue(capa.auto_raised)
        self.assertEqual(capa.source, "endline")
        self.assertEqual(capa.line_ids, self.line)
        self.assertEqual(len(capa.inspection_ids), 2)
        self.assertIn("recorded 10 times", capa.message_ids[0].body)
        self.assertEqual(capa.raised_from, "End-line checks, QA Line 9")

    def test_open_capa_is_updated_not_duplicated(self):
        self.inspect(kind="endline", pieces=50, defects=[(self.d_major, 10, "left_sleeve")])
        self.inspect(kind="endline", pieces=50, defects=[(self.d_major, 4, "left_sleeve")])
        capa = self.capas()
        self.assertEqual(len(capa), 1)
        self.assertEqual(capa.occurrences, 14)
        self.assertEqual(capa.occurrences_label, "14 in 3 days")

    def test_other_place_or_old_defects_do_not_count_toward_capa(self):
        self.inspect(kind="endline", pieces=50, defects=[(self.d_major, 5, "left_sleeve"), (self.d_major, 5, "hem")])
        old = fields.Datetime.now() - timedelta(days=4)
        insp = self.inspect(kind="endline", pieces=50, date=old)
        self.env["garment.inspection.defect"].create({"inspection_id": insp.id, "defect_id": self.d_major.id,
                                                      "position": "left_sleeve", "qty": 5, "date": old})
        self.assertFalse(self.capas())

    def test_capa_threshold_comes_from_the_company(self):
        self.company.garment_capa_threshold = 3
        self.inspect(kind="inline", pieces=20, defects=[(self.d_major, 3, "collar")])
        self.assertEqual(len(self.capas()), 1)

    def test_capa_closes_only_with_root_cause_action_and_owner(self):
        capa = self.env["garment.capa"].create({"title": "QA capa", "source": "other"})
        with self.assertRaises(UserError):
            capa.action_close()
        capa.action_start()
        with self.assertRaises(UserError):
            capa.action_verify()
        capa.write({"root_cause": "Needle worn", "action": "Change needle", "owner_id": self.manager.id,
                    "due_date": self.today + timedelta(days=3)})
        self.assertEqual(capa.due_in_days, 3)
        capa.action_verify()
        self.assertEqual(capa.state, "verified")
        capa.action_close()
        self.assertEqual(capa.state, "closed")
        self.assertTrue(capa.name.startswith("CAPA/"))
