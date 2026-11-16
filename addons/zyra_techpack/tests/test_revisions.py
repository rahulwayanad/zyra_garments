from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, tagged

from .common import TechpackCase


@tagged("post_install", "-at_install", "zyra")
class TestRevisions(TechpackCase):

    def test_first_revision_is_v1_and_named_after_style_code(self):
        self.assertEqual(self.techpack.revision, 1)
        self.assertEqual(self.techpack.name, "ZT-0001 · v1")
        self.assertEqual(self.techpack.state, "draft")

    def test_style_has_only_one_open_revision(self):
        with self.assertRaises(ValidationError):
            self.env["zyra.techpack"].create({"style_id": self.style.id})

    def test_new_version_refused_while_a_revision_is_open(self):
        with self.assertRaises(UserError):
            self.techpack.action_new_revision()

    def test_new_version_copies_lines_and_increments_revision(self):
        self.approve(self.techpack)
        action = self.techpack.with_user(self.designer).action_new_revision()
        v2 = self.env["zyra.techpack"].browse(action["res_id"])
        self.assertEqual(v2.revision, 2)
        self.assertEqual(v2.name, "ZT-0001 · v2")
        self.assertEqual(v2.state, "draft")
        self.assertEqual(len(v2.bom_line_ids), 4)
        self.assertEqual(len(v2.measurement_ids), 2)
        self.assertEqual(len(v2.operation_ids), 2)
        self.assertEqual(v2.sam, self.techpack.sam)
        self.assertFalse(v2.bom_id)

    def test_old_revision_stays_approved_until_new_one_is_approved(self):
        self.approve(self.techpack)
        v2 = self.env["zyra.techpack"].browse(self.techpack.action_new_revision()["res_id"])
        v2.with_user(self.designer).action_submit()
        self.assertEqual(self.techpack.state, "approved")
        self.assertEqual(self.style.current_techpack_id, self.techpack)
        self.assertTrue(self.style.approved_for_production)
        v2.with_user(self.manager).action_approve()
        self.assertEqual(self.techpack.state, "superseded")
        self.assertEqual(v2.state, "approved")
        self.assertEqual(self.style.current_techpack_id, v2)

    def test_approved_tech_pack_cannot_be_edited(self):
        self.approve(self.techpack)
        with self.assertRaises(UserError):
            self.techpack.bom_line_ids[0].consumption = 9.0
        with self.assertRaises(UserError):
            self.techpack.measurement_ids[0].base_value = 1.0
        with self.assertRaises(UserError):
            self.techpack.write({"operation_ids": [Command.create({"operation_id": self.op1.id})]})
        with self.assertRaises(UserError):
            self.techpack.construction_ids.unlink()
        with self.assertRaises(UserError):
            self.techpack.base_size_id = self.l
        with self.assertRaises(UserError):
            self.techpack.unlink()

    def test_only_factory_manager_approves(self):
        self.techpack.with_user(self.merchandiser).action_submit()
        with self.assertRaises(AccessError):
            self.techpack.with_user(self.designer).action_approve()
        with self.assertRaises(AccessError):
            self.techpack.with_user(self.merchandiser).action_approve()
        self.techpack.with_user(self.manager).action_approve()
        self.assertEqual(self.techpack.state, "approved")
        self.assertEqual(self.techpack.approved_user_id, self.manager)

    def test_merchandiser_can_submit_but_not_edit_lines(self):
        with self.assertRaises(AccessError):
            self.techpack.bom_line_ids[0].with_user(self.merchandiser).consumption = 3.0
        self.techpack.with_user(self.merchandiser).action_submit()
        self.assertEqual(self.techpack.state, "submitted")

    def test_submit_needs_materials(self):
        style = self.env["garment.style"].create({"name": "Empty", "code": "ZT-0002",
                                                  "size_range_id": self.size_range.id})
        techpack = self.env["zyra.techpack"].create({"style_id": style.id})
        with self.assertRaises(UserError):
            techpack.with_user(self.designer).action_submit()

    def test_submitted_can_go_back_to_draft_and_approve_needs_submitted(self):
        with self.assertRaises(UserError):
            self.techpack.with_user(self.manager).action_approve()
        self.techpack.with_user(self.designer).action_submit()
        self.techpack.with_user(self.designer).action_reset_draft()
        self.assertEqual(self.techpack.state, "draft")

    def test_style_stage_follows_tech_pack(self):
        style = self.env["garment.style"].create({"name": "Stage", "code": "ZT-0003"})
        self.assertEqual(style.stage, "draft")
        self.assertEqual(self.style.stage, "development")
        self.approve(self.techpack)
        self.assertEqual(self.style.stage, "approved")

    def test_style_sam_is_sum_of_current_tech_pack_operations(self):
        self.assertAlmostEqual(self.techpack.sam, 1.5)
        self.assertEqual(self.style.sam, 0.0, "no approved tech pack yet")
        self.approve(self.techpack)
        self.assertAlmostEqual(self.style.sam, 1.5)

    def test_operation_line_takes_defaults_from_library(self):
        line = self.techpack.operation_ids.filtered(lambda o: o.operation_id == self.op2)
        self.assertEqual(line.name, "Side seams")
        self.assertAlmostEqual(line.sam, 1.1)

    def test_measurement_tolerance_defaults_from_pom(self):
        chest = self.techpack.measurement_ids.filtered(lambda m: m.pom_id == self.pom_chest)
        self.assertEqual((chest.tol_plus, chest.tol_minus), (1.0, 1.0))
        length = self.techpack.measurement_ids.filtered(lambda m: m.pom_id == self.pom_length)
        self.assertEqual((length.tol_plus, length.tol_minus), (1.5, 1.0))

    def test_style_form_edits_lines_of_the_open_revision(self):
        with Form(self.style) as form:
            with form.bom_line_ids.new() as line:
                line.product_id = self.label
                line.material_kind = "packing"
                line.consumption = 1.0
        self.assertEqual(len(self.techpack.bom_line_ids), 5)

    def test_copy_tech_pack_starts_new_style_with_draft_v1(self):
        self.approve(self.techpack)
        action = self.style.action_copy_techpack()
        new_style = self.env["garment.style"].browse(action["res_id"])
        self.assertNotEqual(new_style, self.style)
        self.assertEqual(len(new_style.techpack_ids), 1)
        self.assertEqual(new_style.techpack_ids.revision, 1)
        self.assertEqual(new_style.techpack_ids.state, "draft")
        self.assertEqual(len(new_style.techpack_ids.bom_line_ids), 4)

    def test_bom_line_colour_must_be_a_colourway_of_the_style(self):
        other = self.env["garment.colour"].create({"name": "Other", "code": "TOT"})
        with self.assertRaises(ValidationError):
            self.techpack.bom_line_ids[0].colour_id = other

    def test_cost_per_piece_includes_wastage(self):
        navy_line = self.techpack.bom_line_ids.filtered(lambda ln: ln.colour_id == self.navy)
        # 1.2 m × 1.05 × 2.00
        self.assertAlmostEqual(navy_line.qty_with_wastage, 1.26)
        self.assertAlmostEqual(navy_line.cost_per_piece, 2.52)
        # dearest colourway: navy 2.52 + label 0.05 + button (XL only) 2 × 1.5 × 0.10 = 2.87
        self.assertAlmostEqual(self.techpack.material_cost, 2.87)

    def test_tech_pack_report_renders(self):
        self.approve(self.techpack)
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            "zyra_techpack.action_report_techpack", self.techpack.ids)
        self.assertIn(b"Tech Pack", html)
        self.assertIn(b"ZT-0001", html)
        self.assertIn(b"Test chest", html)
