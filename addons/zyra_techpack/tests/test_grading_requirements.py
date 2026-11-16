from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TechpackCase


@tagged("post_install", "-at_install", "zyra")
class TestGradingRequirements(TechpackCase):

    def test_graded_value_is_base_plus_steps_times_grade_rule(self):
        chart = self.techpack.get_graded_chart()
        chest = chart[self.pom_chest.id]
        self.assertEqual(chest[self.m.id], 50.0, "base size keeps the base value")
        self.assertEqual(chest[self.s.id], 47.5)
        self.assertEqual(chest[self.l.id], 52.5)
        self.assertEqual(chest[self.xl.id], 55.0)
        length = chart[self.pom_length.id]
        self.assertEqual([length[s.id] for s in (self.s, self.m, self.l, self.xl)], [68.0, 70.0, 72.0, 74.0])

    def test_changing_base_size_regrades_the_chart(self):
        self.techpack.base_size_id = self.xl
        chest = self.techpack.get_graded_chart()[self.pom_chest.id]
        self.assertEqual(chest[self.xl.id], 50.0)
        self.assertEqual(chest[self.s.id], 42.5)

    def test_graded_chart_marks_base_size(self):
        html = str(self.techpack.graded_chart_html)
        self.assertIn("M *", html)
        self.assertIn("o_zyra_base_size", html)
        self.assertIn("55.00", html)

    def test_base_size_must_be_in_style_size_range(self):
        other_range = self.env["garment.size.range"].create({"name": "Other", "size_ids": [(0, 0, {"name": "Z"})]})
        with self.assertRaises(ValidationError):
            self.techpack.base_size_id = other_range.size_ids

    def test_material_requirements_net_and_with_wastage_per_colourway(self):
        reqs = self.techpack.material_requirements({
            (self.navy.id, self.m.id): 100,
            (self.navy.id, self.xl.id): 50,
            (self.white, self.s): 200,   # records are accepted too
        })
        by_key = {(r["product_id"], r["colour_id"]): r for r in reqs}
        navy_fabric = by_key[(self.fabric.id, self.navy.id)]
        self.assertAlmostEqual(navy_fabric["qty_net"], 150 * 1.2)
        self.assertAlmostEqual(navy_fabric["qty_with_wastage"], 150 * 1.2 * 1.05)
        self.assertEqual(navy_fabric["uom_id"], self.env.ref("uom.product_uom_meter").id)
        white_fabric = by_key[(self.fabric.id, self.white.id)]
        self.assertAlmostEqual(white_fabric["qty_net"], 200.0)
        self.assertAlmostEqual(white_fabric["qty_with_wastage"], 220.0)

    def test_material_requirements_all_colour_line_applies_to_every_colourway(self):
        reqs = self.techpack.material_requirements({(self.navy.id, self.m.id): 10, (self.white.id, self.m.id): 30})
        labels = {r["colour_id"]: r["qty_net"] for r in reqs if r["product_id"] == self.label.id}
        self.assertEqual(labels, {self.navy.id: 10.0, self.white.id: 30.0})

    def test_material_requirements_size_line_only_for_that_size(self):
        reqs = self.techpack.material_requirements({(self.navy.id, self.m.id): 10, (self.navy.id, self.xl.id): 4})
        buttons = [r for r in reqs if r["product_id"] == self.button.id]
        self.assertEqual(len(buttons), 1)
        self.assertAlmostEqual(buttons[0]["qty_net"], 8.0)
        self.assertAlmostEqual(buttons[0]["qty_with_wastage"], 12.0)
        self.assertEqual(set(buttons[0]), {"product_id", "colour_id", "uom_id", "qty_net", "qty_with_wastage",
                                           "material_kind", "price_unit"})
