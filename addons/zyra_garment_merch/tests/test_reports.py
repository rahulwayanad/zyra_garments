from datetime import timedelta

from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestReports(MerchCase):

    def test_printed_documents_render(self):
        order = self.make_order()
        sample = self.env["garment.sample"].create({"style_id": self.style.id, "size_measured_id": self.m.id,
                                                    "required_date": self.today + timedelta(days=3)})
        sample.action_load_spec()
        card = self.env["garment.approval"].create({"style_id": self.style.id, "colour_id": self.red.id})
        Report = self.env["ir.actions.report"]
        for xmlid, rec, text in (
                ("zyra_garment_merch.action_report_order_breakdown", order, order.name),
                ("zyra_garment_merch.action_report_sample_ticket", sample, sample.name),
                ("zyra_garment_merch.action_report_sample_fit", sample, "Merch chest"),
                ("zyra_garment_merch.action_report_approval_card", card, card.name)):
            html, _fmt = Report._render_qweb_html(xmlid, rec.ids)
            self.assertIn(text, html.decode())
