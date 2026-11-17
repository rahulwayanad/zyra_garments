from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import CuttingCase


@tagged("post_install", "-at_install", "zyra")
class TestBundle(CuttingCase):

    def _bundled_lay(self, rolls=None, bundle_size=40):
        plan = self.make_plan(bundle_size=bundle_size)
        plan.action_propose()
        plan.action_approve()
        lay = plan.lay_ids.sorted("lay_no")[0]  # MIX S:1 M:2 L:1, 80 plies
        self.cut_lay(lay, rolls)
        lay.action_create_bundles()
        return lay

    def test_bundles_split_by_plies_roll_and_bundle_size(self):
        lay = self._bundled_lay([(self.roll_a, 50), (self.roll_b, 30)], bundle_size=40)
        bundles = lay.bundle_ids
        # each size copy: roll A plies 1-40, 41-50; roll B plies 51-80 -> 3 bundles × 4 copies
        self.assertEqual(len(bundles), 12)
        for size, ratio in ((self.s, 1), (self.m, 2), (self.l, 1)):
            self.assertEqual(sum(bundles.filtered(lambda b: b.size_id == size).mapped("pieces")), 80 * ratio)
        self.assertEqual(sum(bundles.mapped("pieces")), lay.pieces)
        self.assertTrue(all(b.pieces <= 40 for b in bundles))
        on_b = bundles.filtered(lambda b: b.roll_id == self.roll_b)
        self.assertTrue(all(b.shade == "B" and b.ply_from == 51 and b.ply_to == 80 for b in on_b))
        self.assertEqual(sorted(bundles.mapped("bundle_no")), list(range(1, 13)))

    def test_bundle_size_zero_makes_one_bundle_per_size_copy_and_roll(self):
        lay = self._bundled_lay(bundle_size=0)
        self.assertEqual(len(lay.bundle_ids), 4)
        self.assertTrue(all(b.pieces == 80 for b in lay.bundle_ids))
        self.assertEqual(lay.bundle_ids[0].plies_label, "1 – 80")

    def test_bundle_gets_one_coupon_per_techpack_operation(self):
        bundle = self._bundled_lay().bundle_ids[0]
        self.assertEqual(bundle.operation_count, 2)
        self.assertEqual(bundle.coupon_ids.mapped("operation_line_id"), self.techpack.operation_ids)
        self.assertEqual(bundle.coupon_ids.sorted("sequence").mapped("sequence"), [1, 2])

    def test_coupon_payload_round_trip(self):
        bundle = self._bundled_lay().bundle_ids[0]
        coupon = bundle.coupon_ids[0]
        payload = coupon.payload
        parts = payload.split("|")
        self.assertEqual(parts[:3], ["ZG1", str(bundle.id), str(coupon.operation_line_id.id)])
        self.assertEqual(len(parts[3]), 6)
        found_bundle, operation = self.env["garment.bundle"]._garment_parse_coupon(payload)
        self.assertEqual(found_bundle, bundle)
        self.assertEqual(operation, coupon.operation_line_id)
        self.assertEqual(self.env["garment.bundle"]._garment_coupon_from_payload(" %s\n" % payload), coupon)

    def test_coupon_with_bad_checksum_or_format_is_refused(self):
        bundle = self._bundled_lay().bundle_ids[0]
        payload = bundle.coupon_ids[0].payload
        Bundle = self.env["garment.bundle"]
        bad_check = payload[:-1] + ("0" if payload[-1] != "0" else "1")
        for bad in (bad_check, "ZG2" + payload[3:], "B0000781", "", "ZG1|x|1|ABCDEF",
                    "ZG1|%d|999999|%s" % (bundle.id, Bundle._garment_coupon_check(bundle.id, 999999)),
                    "ZG1|999999|1|%s" % Bundle._garment_coupon_check(999999, 1)):
            with self.assertRaises(UserError, msg=bad):
                Bundle._garment_parse_coupon(bad)

    def test_coupon_scanned_once_second_scan_refused_with_who(self):
        bundle = self._bundled_lay().bundle_ids[0]
        coupon = bundle.coupon_ids[0]
        coupon._garment_record_scan(self.operator)
        self.assertEqual(bundle.stage, "in_sewing")
        self.assertEqual(coupon.pieces, bundle.pieces)
        with self.assertRaisesRegex(ValidationError, "Cut Test Operator"):
            coupon._garment_record_scan(self.operator)

    def test_last_coupon_moves_bundle_to_sewn(self):
        bundle = self._bundled_lay().bundle_ids[0]
        bundle.action_issue(self.line)
        first, last = bundle.coupon_ids.sorted("sequence")
        self.assertFalse(first._garment_record_scan(self.operator))
        self.assertEqual(bundle.operations_scanned, 1)
        self.assertTrue(last._garment_record_scan(self.operator, rejected=2, reason="Open seam"))
        self.assertEqual(bundle.stage, "sewn")
        self.assertEqual(bundle.rejected_qty, 2)
        self.assertEqual(bundle.good_pieces, bundle.pieces - 2)
        self.assertEqual(bundle.rejected_coupon_ids, last)
        bundle.action_finish()
        self.assertEqual(bundle.board_column, "sewn_finished")

    def test_bundle_cannot_be_marked_sewn_with_unscanned_operations(self):
        bundle = self._bundled_lay().bundle_ids[0]
        bundle.action_issue(self.line)
        bundle.action_start_sewing()
        with self.assertRaises(UserError):
            bundle.action_mark_sewn()

    def test_issue_bundles_to_line(self):
        lay = self._bundled_lay()
        wizard = self.env["garment.bundle.issue"].with_user(self.supervisor).create({
            "bundle_ids": [Command.set(lay.bundle_ids.ids)], "line_id": self.line.id})
        wizard.action_issue()
        self.assertTrue(all(b.stage == "issued" and b.line_id == self.line for b in lay.bundle_ids))
        with self.assertRaises(UserError):
            lay.bundle_ids[0].action_issue(self.line)

    def test_split_bundle_keeps_pieces_and_ply_ranges_contiguous(self):
        bundle = self._bundled_lay().bundle_ids.filtered(lambda b: b.pieces == 40)[0]
        new = bundle._split(15)
        self.assertEqual(bundle.pieces + new.pieces, 40)
        self.assertEqual(new.ply_from, bundle.ply_to + 1)
        self.assertEqual(new.pieces, 15)
        self.assertEqual(new.operation_count, 2)
        self.assertNotEqual(new.name, bundle.name)

    def test_scanned_bundle_cannot_be_split(self):
        bundle = self._bundled_lay().bundle_ids[0]
        bundle.coupon_ids[0]._garment_record_scan(self.operator)
        with self.assertRaises(UserError):
            bundle._split(5)

    def test_bundle_count_on_the_production_order(self):
        lay = self._bundled_lay()
        self.assertEqual(self.order.bundle_count, len(lay.bundle_ids))
        action = self.order.action_view_bundles()
        self.assertEqual(self.env["garment.bundle"].search_count(action["domain"]), len(lay.bundle_ids))

    def test_ticket_report_prints_a_qr_coupon_per_operation(self):
        bundle = self._bundled_lay().bundle_ids[0]
        html, _fmt = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_cutting.action_report_bundle_ticket", bundle.ids)
        html = html.decode()
        self.assertIn(bundle.name, html)
        self.assertIn("Join shoulders", html)
        self.assertGreaterEqual(html.count("data:image/"), 1 + bundle.operation_count)
