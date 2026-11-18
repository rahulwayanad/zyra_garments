from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestSamples(MerchCase):

    def _sample(self, **vals):
        return self.env["garment.sample"].create(dict({
            "style_id": self.style.id, "sample_type": "size_set", "colour_id": self.red.id,
            "size_measured_id": self.l.id, "required_date": self.today + timedelta(days=5)}, **vals))

    def _measure(self, sample, spec, tol_plus, tol_minus, measured):
        return self.env["garment.sample.measurement"].create({
            "sample_id": sample.id, "pom_id": self.pom_chest.id, "spec": spec, "tol_plus": tol_plus,
            "tol_minus": tol_minus, "measured": measured, "round": sample.round})

    def test_point_within_tolerance_passes(self):
        m = self._measure(self._sample(), 50.0, 1.0, 1.0, 50.8)
        self.assertEqual(m.result, "pass")
        self.assertAlmostEqual(m.deviation, 0.8)

    def test_point_on_the_tolerance_limit_passes(self):
        m = self._measure(self._sample(), 50.0, 1.0, 1.0, 49.0)
        self.assertEqual(m.result, "pass")

    def test_point_outside_tolerance_fails(self):
        m = self._measure(self._sample(), 50.0, 1.0, 1.0, 51.2)
        self.assertEqual(m.result, "fail")

    def test_plus_and_minus_tolerances_apply_on_their_own_side(self):
        sample = self._sample()
        self.assertEqual(self._measure(sample, 70.0, 1.5, 0.5, 71.4).result, "pass")
        self.assertEqual(self._measure(sample, 70.0, 1.5, 0.5, 69.4).result, "fail")

    def test_point_not_measured_has_no_verdict(self):
        m = self._measure(self._sample(), 50.0, 1.0, 1.0, 0.0)
        self.assertEqual(m.result, "pending")

    def test_points_measured_and_out_of_tolerance_count_the_current_round(self):
        sample = self._sample()
        self._measure(sample, 50.0, 1.0, 1.0, 50.5)
        self._measure(sample, 50.0, 1.0, 1.0, 53.0)
        self._measure(sample, 50.0, 1.0, 1.0, 0.0)
        self.assertEqual((sample.points_measured, sample.points_out), (2, 1))

    def test_load_spec_takes_graded_values_for_the_size_measured(self):
        sample = self._sample()
        sample.action_load_spec()
        specs = {m.pom_id: m for m in sample.measurement_ids}
        # base size M; L is one step up: chest 50 + 2.0, length 70 + 1.5
        self.assertAlmostEqual(specs[self.pom_chest].spec, 52.0)
        self.assertAlmostEqual(specs[self.pom_length].spec, 71.5)
        self.assertEqual((specs[self.pom_length].tol_plus, specs[self.pom_length].tol_minus), (1.5, 0.5))
        sample.action_load_spec()
        self.assertEqual(len(sample.measurement_ids), 2, "loading twice does not duplicate points")

    def test_sample_workflow_requested_to_approved_logs_the_round(self):
        sample = self._sample()
        sample.action_start()
        self.assertEqual(sample.state, "in_progress")
        sample.action_send_to_buyer()
        self.assertEqual(sample.state, "with_buyer")
        self.assertEqual(sample.sent_date, self.today)
        sample.action_approve()
        self.assertEqual(sample.state, "approved")
        self.assertEqual(sample.round_ids.decision, "approved")

    def test_rejected_sample_is_remade_in_the_next_round(self):
        sample = self._sample()
        sample.action_start()
        sample.action_send_to_buyer()
        sample.action_reject()
        self.assertEqual(sample.state, "rejected")
        sample.action_remake()
        self.assertEqual((sample.state, sample.round), ("in_progress", 2))
        self.assertFalse(sample.sent_date)
        self.assertEqual(sample.round_ids.mapped("round"), [1])

    def test_only_a_sample_with_the_buyer_can_be_approved(self):
        sample = self._sample()
        with self.assertRaises(UserError):
            sample.action_approve()

    def test_sample_without_buyer_is_approved_in_house_from_the_sample_room(self):
        self.style.buyer_id = False
        sample = self._sample()
        self.assertFalse(sample.buyer_id)
        with self.assertRaises(UserError):
            sample.action_send_to_buyer()
        sample.action_start()
        sample.action_approve()
        self.assertEqual(sample.state, "approved")
        self.assertEqual(sample.round_ids.decision, "approved")

    def test_sample_without_buyer_is_rejected_in_house_and_remade(self):
        self.style.buyer_id = False
        sample = self._sample()
        sample.action_start()
        sample.action_reject()
        self.assertEqual(sample.state, "rejected")
        sample.action_remake()
        self.assertEqual((sample.state, sample.round), ("in_progress", 2))

    def test_sample_with_a_buyer_cannot_skip_the_buyer(self):
        sample = self._sample()
        self.assertTrue(sample.buyer_id)
        sample.action_start()
        with self.assertRaises(UserError):
            sample.action_approve()

    def test_sample_past_required_date_and_not_sent_is_overdue(self):
        sample = self._sample(required_date=self.today - timedelta(days=1))
        self.assertTrue(sample.is_overdue)
        self.assertIn(sample, self.env["garment.sample"].search([("is_overdue", "=", True)]))
        sample.action_start()
        sample.action_send_to_buyer()
        self.assertFalse(sample.is_overdue, "a sample with the buyer is no longer overdue")

    def test_pp_sample_status_shows_on_the_order(self):
        order = self.make_order()
        self.assertFalse(order.pp_sample_ok)
        sample = self._sample(order_id=order.id, sample_type="pp")
        sample.action_start()
        sample.action_send_to_buyer()
        sample.action_approve()
        self.assertTrue(order.pp_sample_ok)
        self.assertEqual(order.pp_sample_status, "Approved")
        self.assertEqual(order.sample_count, 1)

    def test_sample_charged_to_buyer_is_invoiced_once(self):
        sample = self._sample(cost=40.0, charge_to_buyer=True)
        sample.action_invoice_cost()
        self.assertEqual(sample.invoice_id.amount_untaxed, 40.0)
        self.assertEqual(sample.invoice_id.partner_id, self.buyer)
        with self.assertRaises(UserError):
            sample.action_invoice_cost()
