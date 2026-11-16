from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestLate(MerchCase):

    def test_order_past_ex_factory_and_not_shipped_is_late(self):
        order = self.make_order({(self.red, self.s): 10}, ex_days=-3)
        self.assertTrue(order.is_late)
        self.assertEqual(order.days_to_ex_factory, -3)
        self.assertIn(order, self.env["garment.order"].search([("is_late", "=", True)]))
        self.assertNotIn(order, self.env["garment.order"].search([("is_late", "=", False)]))

    def test_order_before_ex_factory_is_not_late(self):
        order = self.make_order(ex_days=5)
        self.assertFalse(order.is_late)
        self.assertEqual(order.days_to_ex_factory, 5)
        self.assertNotIn(order, self.env["garment.order"].search([("is_late", "=", True)]))

    def test_fully_shipped_order_is_not_late(self):
        order = self.make_order({(self.red, self.s): 10}, ex_days=-3)
        order._garment_add_progress("shipped", self.red.id, self.s.id, 10)
        self.assertEqual(order.state, "shipped")
        self.assertFalse(order.is_late)

    def test_partly_shipped_order_past_ex_factory_stays_late(self):
        order = self.make_order({(self.red, self.s): 10}, ex_days=-1)
        order._garment_add_progress("shipped", self.red.id, self.s.id, 9)
        self.assertTrue(order.is_late)
