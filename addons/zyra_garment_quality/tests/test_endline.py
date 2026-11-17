from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import QualityCase


@tagged("post_install", "-at_install", "zyra")
class TestEndline(QualityCase):

    def test_tablet_counts_good_and_defective_pieces_on_one_daily_session(self):
        Insp = self.env["garment.inspection"]
        stats = Insp.garment_endline_record(self.line.id)
        self.assertEqual(stats["hour_checked"], 1)
        self.assertEqual(stats["hour_dhu"], 0.0)
        for _i in range(3):
            Insp.garment_endline_record(self.line.id)
        stats = Insp.garment_endline_record(self.line.id, self.d_major.id, "left_sleeve")
        self.assertEqual(stats["hour_checked"], 5)
        self.assertEqual(stats["hour_dhu"], 20.0)
        self.assertEqual(stats["today_dhu"], 20.0)
        self.assertEqual(stats["limit"], 5.0)
        session = Insp.search([("kind", "=", "endline"), ("line_id", "=", self.line.id)])
        self.assertEqual(len(session), 1)
        self.assertEqual(session.pieces_checked, 5)
        self.assertEqual(session.defect_line_ids.position, "left_sleeve")
        self.assertEqual(session.hour_ids.pieces, 5)
        self.assertEqual(session.hour_ids.defects, 1)

    def test_tablet_defect_needs_a_place(self):
        with self.assertRaises(UserError):
            self.env["garment.inspection"].garment_endline_record(self.line.id, self.d_major.id, False)

    def test_tablet_state_lists_places_defects_and_the_running_order(self):
        self.d_major.write({"endline_button": True, "endline_label": "Puckering"})
        state = self.env["garment.inspection"].garment_endline_state(self.line.id)
        self.assertEqual(state["order"]["id"], self.order.id)
        self.assertEqual([p["key"] for p in state["positions"]][:2], ["collar", "front_left"])
        self.assertIn("Puckering", [d["label"] for d in state["defects"]])
        lines = self.env["garment.inspection"].garment_endline_lines()
        self.assertIn(self.line.id, [l["id"] for l in lines])

    def test_tablet_refuses_a_line_without_open_order(self):
        idle = self.env["mrp.workcenter"].create({"name": "QA idle line", "code": "QAI"})
        with self.assertRaises(UserError):
            self.env["garment.inspection"].garment_endline_record(idle.id)
