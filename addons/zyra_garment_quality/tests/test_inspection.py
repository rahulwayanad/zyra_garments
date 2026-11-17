from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import QualityCase


@tagged("post_install", "-at_install", "zyra")
class TestInspection(QualityCase):

    def test_dhu_is_defects_times_100_over_pieces_checked(self):
        insp = self.inspect(kind="endline", pieces=32, defects=[(self.d_minor, 5)])
        self.assertAlmostEqual(insp.dhu, 15.63)
        self.assertEqual(insp.dhu_display, "15.6%")
        insp2 = self.inspect(pieces=125, defects=[(self.d_major, 10), (self.d_minor, 4)])
        self.assertAlmostEqual(insp2.dhu, 11.2)
        self.assertEqual((insp2.major_count, insp2.minor_count, insp2.defect_count), (10, 4, 14))

    def test_dhu_is_zero_when_nothing_checked(self):
        self.assertEqual(self.inspect(kind="inline", pieces=0, defects=[(self.d_minor, 1)]).dhu, 0.0)

    def test_defect_class_defaults_from_the_library_and_can_be_changed(self):
        insp = self.inspect(defects=[(self.d_major, 2)])
        line = insp.defect_line_ids
        self.assertEqual(line.severity, "major")
        line.severity = "minor"
        self.assertEqual((insp.major_count, insp.minor_count), (0, 2))

    def test_final_passes_when_majors_equal_the_accept_number(self):
        insp = self.inspect(defects=[(self.d_major, 7), (self.d_minor, 10)], complete=True)
        self.assertEqual((insp.state, insp.result), ("completed", "passed"))
        self.assertFalse(insp.fail_reason)

    def test_final_fails_when_majors_are_above_the_accept_number(self):
        insp = self.inspect(defects=[(self.d_major, 8), (self.d_minor, 4)], complete=True)
        self.assertEqual(insp.result, "failed")
        self.assertEqual(insp.fail_reason, "Major defects above the accept number")

    def test_final_fails_when_minors_are_above_the_accept_number(self):
        insp = self.inspect(defects=[(self.d_minor, 11)], complete=True)
        self.assertEqual(insp.fail_reason, "Minor defects above the accept number")

    def test_any_critical_defect_fails_the_final(self):
        insp = self.inspect(defects=[(self.d_critical, 1)], complete=True)
        self.assertEqual(insp.result, "failed")
        self.assertIn("Critical defect found", insp.fail_reason)

    def test_final_cannot_complete_before_the_sample_is_checked(self):
        insp = self.inspect(pieces=100)
        with self.assertRaises(UserError):
            insp.action_complete()
        self.assertEqual(insp.state, "in_progress")

    def test_inline_and_endline_fail_only_on_critical_defects(self):
        ok = self.inspect(kind="inline", pieces=20, defects=[(self.d_major, 8)], complete=True)
        self.assertEqual(ok.result, "passed")
        bad = self.inspect(kind="endline", pieces=20, defects=[(self.d_critical, 1)], complete=True)
        self.assertEqual(bad.result, "failed")

    def test_inspection_without_pieces_cannot_complete(self):
        with self.assertRaises(UserError):
            self.inspect(kind="inline", pieces=0).action_complete()

    def test_line_and_company_default_from_the_order(self):
        insp = self.inspect(kind="inline")
        self.assertEqual(insp.line_id, self.line)
        self.assertEqual(insp.company_id, self.order.company_id)
        self.assertTrue(insp.name.startswith("QI/"))

    def test_raise_capa_from_inspection_prefills_the_top_defect(self):
        insp = self.inspect(kind="endline", pieces=20, defects=[(self.d_minor, 1), (self.d_major, 3, "hem")],
                            complete=True)
        action = insp.action_raise_capa()
        ctx = action["context"]
        self.assertEqual(ctx["default_defect_id"], self.d_major.id)
        self.assertEqual(ctx["default_position"], "hem")
        self.assertEqual(ctx["default_occurrences"], 3)
        capa = self.env["garment.capa"].with_context(**ctx).create({})
        self.assertEqual(capa.inspection_ids, insp)
        self.assertEqual(insp.capa_count, 1)
