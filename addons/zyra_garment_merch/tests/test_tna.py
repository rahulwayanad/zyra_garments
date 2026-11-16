from datetime import timedelta

from odoo.tests import tagged

from .common import MerchCase


@tagged("post_install", "-at_install", "zyra")
class TestTimeAndAction(MerchCase):

    def test_template_milestones_are_laid_back_from_ex_factory(self):
        order = self.make_order(ex_days=30, tna_template_id=self.template.id)
        self.assertEqual(len(order.milestone_ids), 3, "confirming applies the template")
        planned = {m.name: m.planned_date for m in order.milestone_ids}
        ex = order.ex_factory_date
        self.assertEqual(planned["Order confirmed"], ex - timedelta(days=40))
        self.assertEqual(planned["Cutting started"], ex - timedelta(days=20))
        self.assertEqual(planned["Goods handed over"], ex)
        self.assertEqual(order.milestone_ids.mapped("owner_id"), order.merchandiser_id)

    def test_milestone_done_on_plan_is_on_time_and_after_plan_is_late(self):
        order = self.make_order(ex_days=30, tna_template_id=self.template.id)
        first, second = order.milestone_ids.sorted("planned_date")[:2]
        first.actual_date = first.planned_date
        second.actual_date = second.planned_date + timedelta(days=2)
        self.assertEqual(first.status, "on_time")
        self.assertEqual((second.status, second.delay_days, second.status_label), ("late", 2, "Late 2 d"))

    def test_milestone_not_done_past_its_date_is_overdue(self):
        order = self.make_order(ex_days=30, tna_template_id=self.template.id)
        first = order.milestone_ids.sorted("planned_date")[0]  # ex - 40 = 10 days ago
        last = order.milestone_ids.sorted("planned_date")[-1]
        self.assertEqual(first.status, "overdue")
        self.assertEqual(last.status, "pending")
        self.assertEqual(order.milestone_overdue_count, 1)
        self.assertIn(first, self.env["garment.tna.milestone"].search([("status", "=", "overdue")]))

    def test_moving_ex_factory_reschedules_open_milestones_only(self):
        order = self.make_order(ex_days=30, tna_template_id=self.template.id)
        done = order.milestone_ids.sorted("planned_date")[0]
        done.actual_date = done.planned_date
        kept = done.planned_date
        order.ex_factory_date = order.ex_factory_date + timedelta(days=7)
        self.assertEqual(done.planned_date, kept)
        handover = order.milestone_ids.filtered(lambda m: m.name == "Goods handed over")
        self.assertEqual(handover.planned_date, order.ex_factory_date)

    def test_milestones_done_count_feeds_the_order_kpi(self):
        order = self.make_order(ex_days=30, tna_template_id=self.template.id)
        order.milestone_ids[0].action_mark_done()
        self.assertEqual((order.milestone_done_count, order.milestone_count), (1, 3))
