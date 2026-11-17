import base64

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .common import CuttingCase


@tagged("post_install", "-at_install", "zyra")
class TestCutPlan(CuttingCase):

    def test_to_cut_adds_extra_cut_percent_per_size_rounded_up(self):
        plan = self.make_plan()
        by_size = {l.size_id: l for l in plan.size_line_ids}
        self.assertEqual(by_size[self.s].qty_ordered, 100)
        self.assertEqual(by_size[self.s].qty_to_cut, 103)
        self.assertEqual(by_size[self.m].qty_to_cut, 206)
        self.assertEqual(by_size[self.l].qty_to_cut, 155)  # 154.5 rounds up
        self.assertEqual(plan.qty_ordered, 450)
        self.assertEqual(plan.qty_to_cut, 464)

    def test_plan_size_lines_follow_the_order_sizes_in_order(self):
        plan = self.make_plan()
        self.assertEqual(plan.size_line_ids.mapped("size_id"), self.s | self.m | self.l)

    def test_fabric_comes_from_the_techpack_and_required_uses_consumption_with_wastage(self):
        plan = self.make_plan()
        self.assertEqual(plan.fabric_id, self.fabric)
        self.assertAlmostEqual(plan.fabric_required, 464 * 1.2 * 1.05, places=2)

    def test_lay_proposal_covers_every_size_exactly(self):
        plan = self.make_plan()
        plan.action_propose()
        self.assertEqual(plan.qty_planned, plan.qty_to_cut)
        self.assertEqual(plan.qty_short, 0)
        self.assertEqual(plan.qty_overcut, 0)
        self.assertEqual(plan.planned_pct, 100.0)
        for line in plan.size_line_ids:
            self.assertEqual(line.qty_planned, line.qty_to_cut, line.size_id.name)
            self.assertEqual(line.qty_left, 0)

    def test_proposal_respects_maximum_plies_per_lay(self):
        plan = self.make_plan(max_plies=30)
        plan.action_propose()
        self.assertTrue(all(p.plies <= 30 for p in plan.proposal_ids))
        self.assertEqual(plan.qty_planned, plan.qty_to_cut)

    def test_proposal_prefers_the_marker_that_cuts_most_pieces(self):
        plan = self.make_plan()
        plan.action_propose()
        first = plan.proposal_ids.sorted("sequence")[0]
        self.assertEqual(first.marker_id, self.marker_mix)
        self.assertEqual(first.plies, 80)
        self.assertEqual(first.pieces, 320)

    def test_proposal_never_overcuts_without_single_size_markers(self):
        self.single[self.s].active = False
        self.single[self.m].active = False
        plan = self.make_plan()
        plan.action_propose()
        self.assertEqual(plan.qty_overcut, 0)
        for line in plan.size_line_ids:
            self.assertLessEqual(line.qty_planned, line.qty_to_cut)

    def test_proposed_lay_fabric_is_plies_times_length_plus_end_allowance(self):
        plan = self.make_plan(end_allowance_m=0.05)
        plan.action_propose()
        proposal = plan.proposal_ids.sorted("sequence")[0]
        self.assertAlmostEqual(proposal.fabric, 80 * (4.0 + 0.05), places=2)
        self.assertAlmostEqual(plan.fabric_to_lay, sum(plan.proposal_ids.mapped("fabric")), places=2)

    def test_approving_plan_creates_one_lay_per_proposed_lay(self):
        plan = self.make_plan()
        plan.action_propose()
        plan.action_approve()
        self.assertEqual(plan.state, "approved")
        self.assertEqual(len(plan.lay_ids), len(plan.proposal_ids))
        lay = plan.proposal_ids.sorted("sequence")[0].lay_id
        self.assertEqual(lay.plies_planned, 80)
        self.assertEqual(lay.marker_id, self.marker_mix)
        tail = self.order.name.rsplit("/", 1)[-1]
        self.assertEqual(sorted(plan.lay_ids.mapped("name"))[0], "%s-C01" % tail)

    def test_plan_cannot_be_approved_without_lays(self):
        plan = self.make_plan()
        with self.assertRaises(UserError):
            plan.action_approve()

    def test_proposed_lay_above_maximum_plies_is_refused_on_approval(self):
        plan = self.make_plan()
        plan.action_propose()
        plan.proposal_ids.sorted("sequence")[0].plies = 120
        with self.assertRaises(UserError):
            plan.action_approve()

    def test_one_open_plan_per_order_and_colourway(self):
        self.make_plan()
        with self.assertRaises(ValidationError):
            self.make_plan()

    def test_plan_needs_a_colourway_of_the_order(self):
        green = self.env["garment.colour"].create({"name": "Cut Green", "code": "CGR"})
        with self.assertRaises(ValidationError):
            self.make_plan(colour=green)

    def test_builder_edited_plies_update_left_to_plan_and_approve(self):
        plan = self.make_plan()
        action = plan.action_open_builder()
        builder = self.env["garment.cut.plan.builder"].browse(action["res_id"])
        self.assertEqual(builder.left_to_plan, 0)
        self.assertEqual(builder.pieces, 464)
        with Form(builder) as form:
            with form.line_ids.edit(0) as line:
                line.plies = 79
        self.assertEqual(builder.left_to_plan, 4)  # one ply of S:1 M:2 L:1
        self.assertIn("Left to plan", builder.sizes_html)
        builder.action_approve()
        self.assertEqual(plan.state, "approved")
        self.assertEqual(plan.qty_short, 4)
        self.assertEqual(plan.lay_count, len(builder.line_ids))

    def test_builder_reproposes_only_what_is_left_after_existing_lays(self):
        plan = self.make_plan()
        plan.action_propose()
        plan.proposal_ids.sorted("sequence")[-1].unlink()
        plan.action_approve()
        builder = self.env["garment.cut.plan.builder"]._create_for_plan(plan)
        builder.action_repropose()
        builder.action_approve()
        self.assertEqual(plan.qty_short, 0)
        self.assertEqual(plan.qty_planned, plan.qty_to_cut)

    def test_marker_csv_import_creates_and_updates_markers(self):
        csv = "name,ratio,length_m,width_cm,efficiency_pct\nCSV-1,S:1 L:2,3.3,180,81.5\nCSV-2,M:1,1.1,180,76\n"
        wizard = self.env["garment.marker.import"].create({
            "style_id": self.style.id, "file": base64.b64encode(csv.encode())})
        wizard.action_import()
        marker = self.env["garment.marker"].search([("style_id", "=", self.style.id), ("name", "=", "CSV-1")])
        self.assertEqual(marker.pieces_per_ply, 3)
        self.assertEqual(marker.ratio_text, "S × 1 + L × 2")
        self.assertEqual(marker.display_name, "CSV-1 (1:2)")
        wizard2 = self.env["garment.marker.import"].create({
            "style_id": self.style.id,
            "file": base64.b64encode(b"name,ratio,length_m\nCSV-1,S:1 L:1,2.2\n")})
        wizard2.action_import()
        self.assertEqual(self.env["garment.marker"].search_count(
            [("style_id", "=", self.style.id), ("name", "=", "CSV-1")]), 1)
        self.assertEqual(marker.pieces_per_ply, 2)

    def test_marker_csv_with_unknown_size_is_refused(self):
        wizard = self.env["garment.marker.import"].create({
            "style_id": self.style.id, "file": base64.b64encode(b"name,ratio,length_m\nBAD,XXL:1,1.0\n")})
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_single_size_marker_shows_size_and_ratio(self):
        self.assertEqual(self.single[self.m].display_name, "ONE-M (M:1)")

    def test_propose_cut_plan_from_order_opens_one_plan_per_colourway(self):
        action = self.order.action_propose_cut_plan()
        plans = self.order.cut_plan_ids
        self.assertEqual(plans.mapped("colour_id"), self.red | self.blue)
        self.assertTrue(all(p.proposal_ids for p in plans))
        self.assertEqual(action["res_model"], "garment.cut.plan")
        # running it again opens no second plan
        self.order.action_propose_cut_plan()
        self.assertEqual(len(self.order.cut_plan_ids), 2)

    def test_draft_order_cannot_be_planned(self):
        order = self.order.copy()
        with self.assertRaises(UserError):
            order.action_propose_cut_plan()

    def test_cancelled_plan_frees_the_colourway_and_resets_to_draft(self):
        plan = self.make_plan()
        plan.action_propose()
        plan.action_approve()
        plan.action_cancel()
        self.assertTrue(all(l.state == "cancel" for l in plan.lay_ids))
        self.make_plan()
