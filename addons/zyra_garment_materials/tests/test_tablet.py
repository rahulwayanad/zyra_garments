import importlib.util
import unittest

from odoo.tests import HttpCase, tagged

HAS_WEBSOCKET = importlib.util.find_spec("websocket") is not None


@tagged("post_install", "-at_install", "zyra")
class TestInspectionTablet(HttpCase):

    def _roll(self, name):
        metre = self.env.ref("uom.product_uom_meter")
        fabric = self.env["product.product"].create({
            "name": "Tour Fabric", "type": "consu", "is_storable": True, "tracking": "lot",
            "uom_id": metre.id, "uom_po_id": metre.id})
        return self.env["stock.lot"].create({
            "name": name, "product_id": fabric.id, "company_id": self.env.company.id,
            "is_fabric_roll": True, "width_cm": 152.4, "roll_received_qty": 100.0})

    def test_tablet_screen_loads_for_a_logged_in_user(self):
        """The client action is in the backend bundle and its URL opens for a store user."""
        bundle = self.env["ir.qweb"]._get_asset_bundle("web.assets_backend", js=True, css=True)
        urls = [f["url"] for f in bundle.files]
        self.assertTrue(any("inspection_tablet/inspection_tablet.js" in u for u in urls))
        self.assertTrue(any("inspection_tablet/inspection_tablet.xml" in u for u in urls))
        self.authenticate("admin", "admin")
        response = self.url_open("/odoo/action-zyra_garment_materials.action_fabric_inspection_tablet")
        self.assertEqual(response.status_code, 200)
        action = self.env.ref("zyra_garment_materials.action_fabric_inspection_tablet")
        self.assertEqual(action.tag, "zyra_fabric_inspection_tablet")

    def test_tablet_queue_lists_rolls_waiting_for_inspection(self):
        roll = self._roll("RTQUEUE1")
        queue = self.env["garment.fabric.inspection"].tablet_queue()
        self.assertIn(roll.id, [r["id"] for r in queue["rolls"]])
        insp_id = self.env["garment.fabric.inspection"].tablet_start(roll.id)
        queue = self.env["garment.fabric.inspection"].tablet_queue()
        self.assertNotIn(roll.id, [r["id"] for r in queue["rolls"]])
        self.assertIn(insp_id, [i["id"] for i in queue["inspections"]])

    @unittest.skipUnless(HAS_WEBSOCKET, "the browser tour needs the websocket-client package in the Odoo venv")
    def test_tablet_inspection_tour_records_a_defect_and_finishes(self):
        roll = self._roll("RTOUR01")
        self.start_tour("/odoo/action-zyra_garment_materials.action_fabric_inspection_tablet",
                        "zyra_fabric_inspection_tablet_tour", login="admin")
        insp = self.env["garment.fabric.inspection"].search([("lot_id", "=", roll.id)])
        self.assertEqual(insp.state, "done")
        self.assertEqual(insp.penalty_points, 4)
        self.assertEqual(roll.roll_status, "approved")
