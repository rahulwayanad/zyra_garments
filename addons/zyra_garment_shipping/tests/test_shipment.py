from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ShippingCase


@tagged("post_install", "-at_install", "zyra")
class TestShipment(ShippingCase):

    def setUp(self):
        super().setUp()
        # With zyra_garment_quality installed, an order without a passed final inspection blocks ex-factory.
        # These tests are about shipping, so treat the final as passed, except in the tests about that rule.
        Order = self.env["garment.order"]
        if "final_passed" in Order._fields and self._testMethodName not in (
                "test_final_passed_is_read_only_when_quality_defines_it",
                "test_failed_final_inspection_blocks_shipment_until_manager_override"):
            self.startPatcher(patch.object(type(Order), "_garment_shipping_final_ok", lambda self: True))

    def _packed_shipment(self, lc=None, final=False, cartons=None, **vals):
        order = self.make_order()
        plan = self.make_plan(order)
        plan.action_generate_cartons()
        (cartons and plan.carton_ids.sorted("number")[:cartons] or plan.carton_ids).action_pack()
        ship = self.env["garment.shipment"].create(dict({
            "buyer_id": self.buyer.id, "order_ids": [(6, 0, order.ids)], "lc_id": lc.id if lc else False,
            "final_shipment": final, "planned_date": self.today, "mode": "sea",
        }, **vals))
        ship.action_add_packed_cartons()
        ship.action_confirm()
        return order, plan, ship

    def _lc(self, **vals):
        return self.env["garment.lc"].create(dict({
            "name": "LC-TEST-%s" % len(self.env["garment.lc"].search([])), "buyer_id": self.buyer.id,
            "amount": 1000.0, "tolerance_pct": 5.0, "state": "open",
            "latest_shipment_date": self.today + timedelta(days=20),
            "expiry_date": self.today + timedelta(days=40),
        }, **vals))

    def test_shipment_totals_from_its_cartons(self):
        order, plan, ship = self._packed_shipment()
        self.assertEqual(ship.carton_count, 20)
        self.assertEqual(ship.pieces, 60)
        self.assertAlmostEqual(ship.value, 60 * 5.0)
        self.assertAlmostEqual(ship.volume_cbm, 20 * 0.06)
        self.assertEqual(ship.order_names, order.name)

    def test_days_late_is_actual_minus_planned_ex_factory(self):
        ship = self.env["garment.shipment"].create({
            "buyer_id": self.buyer.id, "planned_date": self.today - timedelta(days=60),
            "actual_date": self.today - timedelta(days=51)})
        self.assertEqual(ship.days_late, 9)
        self.assertEqual(ship.ex_factory_label, "9 d late")
        ship.actual_date = self.today - timedelta(days=61)
        self.assertEqual(ship.days_late, 0)
        self.assertEqual(ship.ex_factory_label, "On time")

    def test_days_late_counts_to_today_while_not_shipped(self):
        ship = self.env["garment.shipment"].create({
            "buyer_id": self.buyer.id, "planned_date": self.today - timedelta(days=4)})
        self.assertEqual(ship.days_late, 4)

    def test_ex_factory_ships_through_a_validated_stock_delivery_and_posts_shipped(self):
        order, plan, ship = self._packed_shipment()
        ship.action_ex_factory()
        self.assertEqual(ship.stage, "ex_factory")
        self.assertEqual(ship.actual_date, self.today)
        self.assertEqual(ship.delivery_count, 1)
        self.assertEqual(ship.picking_ids.state, "done")
        self.assertEqual(sum(ship.picking_ids.move_ids.mapped("quantity")), 60)
        self.assertEqual(order.qty_shipped, 60)
        self.assertEqual(order.state, "shipped")
        self.assertTrue(all(c.state == "shipped" for c in ship.carton_ids))
        self.assertEqual(plan.state, "shipped")

    def test_shipment_moves_through_its_stages_in_order(self):
        order, plan, ship = self._packed_shipment()
        with self.assertRaises(UserError):
            ship.action_on_board()
        ship.action_ex_factory()
        ship.action_handed_over()
        ship.action_on_board()
        ship.action_documents_presented()
        ship.action_paid()
        self.assertEqual(ship.stage, "paid")

    def test_failed_final_inspection_blocks_shipment_until_manager_override(self):
        order, plan, ship = self._packed_shipment()
        with patch.object(type(order), "_garment_shipping_final_ok", lambda self: False):
            ship.invalidate_recordset()
            self.assertEqual(ship.hold_count, 1)
            self.assertIn(order.name, ship.quality_warning)
            with self.assertRaises(UserError):
                ship.action_ex_factory()
            ship.with_user(self.manager)._garment_override("Buyer accepted the re-check on 2 cartons.")
            ship.action_ex_factory()
        self.assertEqual(ship.stage, "ex_factory")
        self.assertIn("Manager override: Buyer accepted", " ".join(ship.message_ids.mapped("body")))

    def test_final_passed_is_read_only_when_quality_defines_it(self):
        order = self.make_order()
        if "final_passed" not in order._fields:
            self.assertTrue(order._garment_shipping_final_ok())
        else:
            self.assertEqual(order._garment_shipping_final_ok(), bool(order.final_passed))

    def test_override_needs_a_factory_manager(self):
        order, plan, ship = self._packed_shipment()
        with self.assertRaises(AccessError):
            ship.with_user(self.packer)._garment_override("I say so")

    def test_override_needs_a_reason(self):
        order, plan, ship = self._packed_shipment()
        with self.assertRaises(UserError):
            ship.with_user(self.manager)._garment_override("   ")

    def test_override_is_logged_in_the_chatter_with_the_reason_and_manager(self):
        lc = self._lc(latest_shipment_date=self.today - timedelta(days=3))
        order, plan, ship = self._packed_shipment(lc=lc)
        wiz = self.env["garment.shipment.override.wizard"].with_user(self.manager).create({
            "shipment_id": ship.id, "reason": "Buyer agreed by e-mail."})
        self.assertIn("after the latest shipment date", wiz.warnings)
        wiz.action_override()
        self.assertEqual(ship.override_user_id, self.manager)
        bodies = " ".join(ship.message_ids.mapped("body"))
        self.assertIn("Manager override: Buyer agreed by e-mail.", bodies)
        self.assertIn("after the latest shipment date", bodies)

    def test_shipping_after_lc_latest_shipment_date_warns_and_needs_override(self):
        lc = self._lc(latest_shipment_date=self.today - timedelta(days=3))
        order, plan, ship = self._packed_shipment(lc=lc)
        self.assertFalse(ship.lc_ok)
        self.assertIn("after the latest shipment date", ship.lc_warning)
        with self.assertRaises(UserError):
            ship.action_ex_factory()

    def test_shipping_under_an_expired_lc_warns(self):
        lc = self._lc(latest_shipment_date=self.today - timedelta(days=20),
                      expiry_date=self.today - timedelta(days=1))
        order, plan, ship = self._packed_shipment(lc=lc)
        self.assertIn("is not open", ship.lc_warning)

    def test_shipment_within_the_lc_ships_without_override(self):
        lc = self._lc()
        order, plan, ship = self._packed_shipment(lc=lc)
        self.assertTrue(ship.lc_ok)
        ship.action_ex_factory()
        self.assertEqual(ship.stage, "ex_factory")

    def test_shipment_value_above_lc_balance_plus_tolerance_warns(self):
        lc = self._lc(amount=200.0)  # 60 pcs × 5 = 300 > 200 × 1.05
        order, plan, ship = self._packed_shipment(lc=lc)
        self.assertIn("above the balance", ship.lc_warning)

    def test_final_shipment_short_beyond_tolerance_warns(self):
        lc = self._lc(tolerance_pct=3.0)
        order, plan, ship = self._packed_shipment(lc=lc, final=True, cartons=10)  # 30 of 60 pieces
        self.assertIn("below the 3% tolerance", ship.lc_warning)

    def test_documents_presented_draws_the_shipment_value_on_the_lc(self):
        lc = self._lc()
        order, plan, ship = self._packed_shipment(lc=lc)
        ship.action_ex_factory()
        ship.action_handed_over()
        ship.action_on_board()
        ship.action_documents_presented()
        self.assertAlmostEqual(lc.drawn, 300.0)
        self.assertAlmostEqual(lc.balance, 700.0)
        self.assertEqual(ship.documents_to_prepare, 0)

    def test_invoice_from_shipment_bills_pieces_at_order_price(self):
        order, plan, ship = self._packed_shipment()
        ship.action_ex_factory()
        ship.action_create_invoice()
        self.assertEqual(ship.invoice_count, 1)
        self.assertAlmostEqual(ship.invoice_ids.amount_untaxed, 300.0)
        with self.assertRaises(UserError):
            ship.action_create_invoice()

    def test_printed_packing_list_renders(self):
        order, plan, ship = self._packed_shipment()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_shipping.report_packing_list", ship.ids)[0]
        self.assertIn(b"Packing List", html)
        self.assertIn(ship.name.encode(), html)
