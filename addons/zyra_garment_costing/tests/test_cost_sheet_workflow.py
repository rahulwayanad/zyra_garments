from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged

from .common import CostingCase


@tagged("post_install", "-at_install", "zyra")
class TestCostSheetWorkflow(CostingCase):

    def _approve(self, sheet, user, reason=None):
        sheet = sheet.with_user(user)
        if reason:
            return sheet.with_context(garment_floor_reason=reason).action_approve()
        return sheet.action_approve()

    def test_sheet_number_comes_from_sequence_and_starts_at_version_one(self):
        sheet = self._sheet()
        self.assertTrue(sheet.name.startswith("CS/"))
        self.assertEqual(sheet.version, 1)
        self.assertEqual(sheet.state, "draft")
        self.assertTrue(sheet.is_latest)

    def test_sheet_above_floor_is_approved_by_costing_without_reason(self):
        sheet = self._sheet(margin_pct=15.0)
        sheet.action_submit()
        self.assertEqual(sheet.state, "submitted")
        self.assertIs(self._approve(sheet, self.costing_user), True)
        self.assertEqual(sheet.state, "approved")
        self.assertEqual(sheet.approved_by_id, self.costing_user)
        self.assertFalse(sheet.floor_override_reason)

    def test_merchandiser_cannot_approve_a_cost_sheet(self):
        sheet = self._sheet(margin_pct=15.0)
        sheet.action_submit()
        with self.assertRaises(AccessError):
            self._approve(sheet, self.merch_user)

    def test_sheet_below_margin_floor_needs_factory_manager_approval(self):
        sheet = self._sheet(margin_pct=5.0)
        sheet.action_submit()
        action = self._approve(sheet, self.costing_user)
        self.assertEqual(action["res_model"], "garment.cost.sheet.approve.wizard",
                         "under the floor the reason wizard opens")
        with self.assertRaises(AccessError):
            self._approve(sheet, self.costing_user, reason="Volume order")
        self.assertEqual(sheet.state, "submitted")

    def test_below_floor_approval_keeps_reason_in_chatter(self):
        sheet = self._sheet(margin_pct=4.5)
        sheet.action_submit()
        action = self._approve(sheet, self.manager)
        wizard = Form(self.env[action["res_model"]].with_user(self.manager).with_context(action["context"]))
        wizard.reason = "Strategic buyer; the line would otherwise stand idle."
        wizard.save().action_confirm()
        self.assertEqual(sheet.state, "approved")
        self.assertEqual(sheet.approved_by_id, self.manager)
        self.assertIn("stand idle", sheet.floor_override_reason)
        bodies = " ".join(sheet.message_ids.mapped("body"))
        self.assertIn("Approved below the margin floor (4.5% against 12.0%)", bodies)
        self.assertIn("stand idle", bodies)

    def test_below_floor_approval_without_reason_is_refused(self):
        sheet = self._sheet(margin_pct=4.5)
        sheet.action_submit()
        with self.assertRaises(UserError):
            sheet.with_user(self.manager)._do_approve(reason="  ")

    def test_approved_sheet_writes_planned_cost_on_techpack(self):
        sheet = self._sheet()
        sheet.action_submit()
        self._approve(sheet, self.costing_user)
        tp = self.techpack
        self.assertEqual(tp.approved_cost_sheet_id, sheet)
        self.assertAlmostEqual(tp.planned_fob_price, sheet.fob_price, places=2)
        self.assertAlmostEqual(tp.planned_cost_per_piece, sheet.total_cost_pc, places=2)
        self.assertAlmostEqual(tp.planned_material_cost, sheet.material_cost_pc, places=2)
        self.assertEqual(self.style.approved_cost_sheet_id, sheet)

    def test_approved_sheet_cannot_change(self):
        sheet = self._sheet()
        sheet.action_submit()
        self._approve(sheet, self.costing_user)
        with self.assertRaises(UserError):
            sheet.margin_pct = 20.0
        with self.assertRaises(UserError):
            sheet.unlink()

    def test_new_version_supersedes_old_sheet_when_approved(self):
        v1 = self._sheet()
        v1.action_submit()
        self._approve(v1, self.costing_user)
        action = v1.with_user(self.merch_user).action_new_version()
        v2 = self.Sheet.browse(action["res_id"])
        self.assertEqual((v2.name, v2.version, v2.state), (v1.name, 2, "draft"))
        self.assertEqual(len(v2.material_line_ids), len(v1.material_line_ids), "lines are copied")
        self.assertFalse(v1.is_latest)
        self.assertTrue(v2.is_latest)
        latest = self.Sheet.search([("name", "=", v1.name), ("is_latest", "=", True)])
        self.assertEqual(latest, v2)
        self.assertEqual(v1.state, "approved", "old version stays approved until the new one is")
        v2.margin_pct = 18.0
        v2.action_submit()
        self._approve(v2, self.costing_user)
        self.assertEqual(v1.state, "superseded")
        self.assertEqual(v2.state, "approved")
        self.assertEqual(self.techpack.approved_cost_sheet_id, v2)
        self.assertEqual(v1.version_ids, v1 | v2)

    def test_new_version_only_from_latest_closed_version(self):
        v1 = self._sheet()
        with self.assertRaises(UserError):
            v1.action_new_version()  # still draft
        v1.action_submit()
        self._approve(v1, self.costing_user)
        v1.action_new_version()
        with self.assertRaises(UserError):
            v1.action_new_version()  # v2 exists

    def test_rejected_sheet_goes_back_to_draft(self):
        sheet = self._sheet()
        sheet.action_submit()
        sheet.with_user(self.costing_user).action_reject()
        self.assertEqual(sheet.state, "rejected")
        sheet.action_reset_draft()
        self.assertEqual(sheet.state, "draft")

    def test_reload_from_techpack_keeps_manual_lines(self):
        sheet = self._sheet()
        manual = self.env["garment.cost.sheet.material"].create({
            "sheet_id": sheet.id, "material_kind": "packing", "method": "manual",
            "product_id": self.label.id, "consumption": 2.0, "price_unit": 0.01,
        })
        sheet.action_load_from_techpack()
        self.assertIn(manual, sheet.material_line_ids)
        self.assertEqual(len(sheet.material_line_ids), 4)

    def test_quotation_uses_fob_price_and_quantity_basis(self):
        sheet = self._sheet()
        sheet.action_submit()
        self._approve(sheet, self.costing_user)
        action = sheet.action_create_quotation()
        order = self.env["sale.order"].browse(action["res_id"])
        self.assertEqual(order.partner_id, self.buyer)
        self.assertEqual(order.order_line.product_uom_qty, 1000)
        self.assertAlmostEqual(order.order_line.price_unit, round(sheet.fob_price, 2), places=2)
        self.assertEqual(sheet.sale_order_ids, order)

    def test_draft_sheet_cannot_be_quoted(self):
        with self.assertRaises(UserError):
            self._sheet().action_create_quotation()

    def test_cost_sheet_report_renders(self):
        sheet = self._sheet()
        html, _fmt = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_garment_costing.action_report_cost_sheet", sheet.ids)
        self.assertIn(sheet.name.encode(), html)
