from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestEndlineTour(HttpCase):

    def test_endline_tablet_loads_and_records_pieces(self):
        env = self.env
        size_range = env["garment.size.range"].create({"name": "QA tour range",
                                                       "size_ids": [Command.create({"name": "M"})]})
        colour = env["garment.colour"].create({"name": "QA tour colour", "code": "QTC"})
        buyer = env["res.partner"].create({"name": "QA tour buyer", "is_garment_buyer": True})
        style = env["garment.style"].create({"name": "QA tour tee", "code": "QA-TOUR", "buyer_id": buyer.id,
                                             "size_range_id": size_range.id,
                                             "colour_ids": [Command.set(colour.ids)]})
        line = env["mrp.workcenter"].create({"name": "QA Tour Line", "code": "QAT"})
        today = fields.Date.today()
        order = env["garment.order"].create({"style_id": style.id, "buyer_id": buyer.id, "sewing_line_id": line.id,
                                             "date_order": today, "ex_factory_date": today + timedelta(days=9)})
        order.line_ids.qty_ordered = 100
        order.state = "in_production"
        env["garment.defect"].create({"code": "QATD", "name": "QA tour defect", "area": "stitching",
                                      "severity": "major", "department": "sewing", "endline_button": True,
                                      "endline_sequence": -1})
        self.start_tour("/odoo/action-zyra_garment_quality.action_endline_check", "zyra_garment_endline_tour",
                        login="admin")
        session = env["garment.inspection"].search([("line_id", "=", line.id), ("kind", "=", "endline")])
        self.assertEqual(session.pieces_checked, 2)
        self.assertEqual(session.defect_count, 1)
