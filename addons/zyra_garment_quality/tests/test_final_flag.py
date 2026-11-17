from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import QualityCase


@tagged("post_install", "-at_install", "zyra")
class TestFinalFlag(QualityCase):

    def test_order_without_final_inspection_is_not_passed(self):
        self.assertEqual(self.order.final_inspection_state, "none")
        self.assertFalse(self.order.final_passed)
        self.inspect(kind="endline", pieces=20, complete=True)
        self.assertEqual(self.order.final_inspection_state, "none")

    def test_failed_final_inspection_blocks_shipment_flag(self):
        insp = self.inspect(defects=[(self.d_major, 8)], complete=True)
        self.assertEqual(self.order.final_inspection_state, "failed")
        self.assertFalse(self.order.final_passed)
        self.assertEqual(self.order.final_inspection_id, insp)
        self.assertIn("shipment is blocked", self.order.message_ids[0].body)

    def test_passing_reinspection_releases_the_order(self):
        failed = self.inspect(defects=[(self.d_major, 8)], complete=True)
        action = failed.action_reinspect()
        again = self.env["garment.inspection"].browse(action["res_id"])
        self.assertEqual(again.reinspection_of_id, failed)
        self.assertEqual(again.lot_size, failed.lot_size)
        self.assertEqual(failed.reinspection_count, 1)
        # An open re-inspection does not change the flag.
        self.assertFalse(self.order.final_passed)
        again.pieces_checked = 125
        again.action_complete()
        self.assertEqual(self.order.final_inspection_state, "passed")
        self.assertTrue(self.order.final_passed)

    def test_latest_final_decides_the_flag(self):
        self.inspect(complete=True)
        self.assertTrue(self.order.final_passed)
        self.inspect(defects=[(self.d_critical, 1)], complete=True)
        self.assertFalse(self.order.final_passed)
        self.assertEqual(self.order.final_inspection_state, "failed")

    def test_only_factory_manager_accepts_a_failed_lot_under_concession(self):
        failed = self.inspect(defects=[(self.d_major, 8)], complete=True)
        with self.assertRaises(UserError):
            failed.with_user(self.quality_user)._garment_accept_concession("Buyer agreed")
        with self.assertRaises(UserError):
            failed.with_user(self.manager)._garment_accept_concession("  ")
        wizard = self.env["garment.inspection.concession.wizard"].with_user(self.manager).create(
            {"inspection_id": failed.id, "reason": "Buyer QA accepted by mail"})
        wizard.action_confirm()
        self.assertEqual(failed.result, "concession")
        self.assertEqual(failed.concession_user_id, self.manager)
        self.assertTrue(self.order.final_passed)
        self.assertEqual(self.order.final_inspection_state, "passed")

    def test_final_passed_is_stored_and_searchable(self):
        self.inspect(complete=True)
        found = self.env["garment.order"].search([("final_passed", "=", True), ("id", "=", self.order.id)])
        self.assertEqual(found, self.order)
