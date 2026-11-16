from datetime import timedelta

from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestStyleFigures(MerchCase):

    def test_open_orders_and_pieces_on_order(self):
        self.make_order({(self.red, self.s): 100})
        self.make_order({(self.blue, self.m): 50}, confirm=False)
        closed = self.make_order({(self.red, self.l): 7})
        closed.with_user(self.manager).action_close()
        self.style.invalidate_recordset()
        self.assertEqual(self.style.open_order_count, 2)
        self.assertEqual(self.style.pieces_on_order, 150)
        self.assertEqual(self.style.order_count, 3)

    def test_samples_and_approvals_pending(self):
        Sample = self.env["garment.sample"]
        s1 = Sample.create({"style_id": self.style.id})
        Sample.create({"style_id": self.style.id})
        s1.action_start()
        s1.action_send_to_buyer()
        s1.action_approve()
        self.env["garment.approval"].create({"style_id": self.style.id})
        self.style.invalidate_recordset()
        self.assertEqual((self.style.sample_count, self.style.samples_pending), (2, 1))
        self.assertEqual((self.style.approval_count, self.style.approvals_pending), (1, 1))

    def test_price_less_material_is_price_minus_material_per_piece(self):
        self.make_order({(self.red, self.s): 10}, price_unit=6.0)
        self.style.invalidate_recordset()
        if "garment.cost.sheet" in self.env:
            self.skipTest("costing installed: the FOB comes from the cost sheet")
        self.assertAlmostEqual(self.style.material_cost, 2.5)
        self.assertAlmostEqual(self.style.costed_fob, 6.0)
        self.assertAlmostEqual(self.style.price_less_material, 3.5)
