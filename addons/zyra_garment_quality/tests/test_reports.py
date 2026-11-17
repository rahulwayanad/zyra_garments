from odoo.tests import tagged

from .common import QualityCase


@tagged("post_install", "-at_install", "zyra")
class TestReports(QualityCase):

    def test_final_inspection_report_shows_plan_defects_and_decision(self):
        insp = self.inspect(defects=[(self.d_major, 8), (self.d_minor, 4)], complete=True)
        html, _fmt = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_quality.action_report_final_inspection", insp.ids)
        html = html.decode()
        self.assertIn("Final Inspection Report %s" % insp.name, html)
        self.assertIn("QA puckering", html)
        self.assertIn("7 / 8", html)
        self.assertIn("Lot rejected. Re-inspection required before shipment.", html)

    def test_capa_report_renders(self):
        capa = self.env["garment.capa"].create({"title": "QA capa report", "source": "endline"})
        html, _fmt = self.env["ir.actions.report"]._render_qweb_html("zyra_garment_quality.action_report_capa",
                                                                      capa.ids)
        self.assertIn("QA capa report", html.decode())
