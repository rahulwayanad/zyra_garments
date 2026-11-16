from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import CostingCase


@tagged("post_install", "-at_install", "zyra")
class TestCostFormulas(CostingCase):

    def test_making_cost_is_sam_times_cost_per_minute_over_efficiency(self):
        making = self.Sheet._formula_making_cost(6.88, 0.0573, 62.0)
        self.assertAlmostEqual(making, 6.88 * 0.0573 / 0.62, places=6)
        self.assertAlmostEqual(making, 0.6358, places=4)
        self.assertEqual(self.Sheet._formula_making_cost(5.0, 0.1, 0.0), 0.0)

    def test_fob_price_grosses_cost_up_by_shares_of_fob(self):
        # 5.00 cost, 3 % commercial, 2 % commission, 15 % margin -> 5 / 0.80
        self.assertAlmostEqual(self.Sheet._formula_fob_price(5.0, 3.0, 2.0, 15.0), 6.25, places=6)

    def test_material_cost_includes_wastage_and_share_of_order(self):
        # 0.70 kg x 1.05 x 6.90 x 25 %
        self.assertAlmostEqual(self.Sheet._formula_material_cost_pc(0.70, 5.0, 6.90, 25.0), 1.267875, places=6)

    def test_order_process_cost_spread_over_quantity_basis(self):
        self.assertAlmostEqual(self.Sheet._formula_process_cost_pc(220.0, "order", 5230), 220 / 5230, places=6)
        self.assertEqual(self.Sheet._formula_process_cost_pc(0.34, "piece", 5230), 0.34)

    def test_margin_at_price_is_what_is_left_after_cost_and_shares(self):
        # cost 4.00 at a price of 5.00 with 3 % commercial: 100 - 3 - 80 = 17 %
        self.assertAlmostEqual(self.Sheet._formula_margin_at_price(4.0, 3.0, 0.0, 5.0), 17.0, places=6)

    def test_making_cost_defaults_from_company_minute_value_and_percent_efficiency(self):
        sheet = self._sheet()
        self.assertEqual(sheet.sam, 4.0, "SAM comes from the tech pack operations")
        self.assertAlmostEqual(sheet.cost_per_minute, 0.10)
        self.assertAlmostEqual(sheet.line_efficiency, 65.0)
        # 4.0 x 0.10 / 0.65 (target efficiency is stored in percent)
        self.assertAlmostEqual(sheet.making_cost_pc, 0.62, places=2)
        self.assertAlmostEqual(sheet.margin_floor_pct, 12.0)

    def test_sheet_loads_materials_from_techpack_with_colourway_share_and_size_average(self):
        sheet = self._sheet()
        lines = sheet.material_line_ids
        self.assertEqual(len(lines), 3, "navy fabric sizes merge into one line")
        navy = lines.filtered(lambda l: l.product_id == self.fabric_navy)
        self.assertEqual(navy.method, "techpack")
        self.assertAlmostEqual(navy.consumption, 0.25, places=4)
        self.assertAlmostEqual(navy.share_pct, 50.0)
        self.assertAlmostEqual(navy.cost_pc, 0.25 * 1.04 * 6.0 * 0.5, places=4)
        label = lines.filtered(lambda l: l.product_id == self.label)
        self.assertEqual(label.material_kind, "trim")
        self.assertAlmostEqual(label.share_pct, 100.0)
        self.assertEqual(sheet.buyer_id, self.buyer, "buyer comes from the style")
        self.assertEqual(sheet.fabric_line_ids, lines - label)
        self.assertEqual(sheet.trim_line_ids, label)

    def test_sheet_totals_with_known_numbers(self):
        sheet = self._sheet(
            sam=6.0, line_efficiency=60.0, cost_per_minute=0.05, quantity_basis=2000,
            overhead_pct=3.0, commission_pct=2.0, margin_pct=15.0, freight_pc=0.20, target_price=5.00,
            process_line_ids=[
                Command.create({"process_type": "print", "charge_basis": "piece", "cost": 0.30}),
                Command.create({"process_type": "testing", "charge_basis": "order", "cost": 200.0}),
            ],
        )
        # fabric: navy 0.25*1.04*6*0.5 = 0.78 ; white 0.25*1.02*5*0.5 = 0.6375
        self.assertAlmostEqual(sheet.fabric_cost_pc, 1.4175, places=2)  # monetary: 2 decimals
        self.assertAlmostEqual(sheet.trim_cost_pc, 0.04, places=2)
        self.assertAlmostEqual(sheet.material_cost_pc, 1.4575, places=2)
        self.assertAlmostEqual(sheet.process_cost_pc, 0.40, places=2)  # 0.30 + 200/2000
        self.assertAlmostEqual(sheet.making_cost_pc, 0.50, places=2)  # 6 x 0.05 / 0.60
        total = 1.4575 + 0.40 + 0.50
        self.assertAlmostEqual(sheet.total_cost_pc, total, places=2)
        fob = total / 0.80
        self.assertAlmostEqual(sheet.fob_price, fob, places=2)
        self.assertAlmostEqual(sheet.margin_amount_pc, fob * 0.15, places=2)
        self.assertAlmostEqual(sheet.overhead_amount_pc, fob * 0.03, places=2)
        self.assertAlmostEqual(sheet.commission_amount_pc, fob * 0.02, places=2)
        self.assertAlmostEqual(sheet.cif_price, fob + 0.20, places=2)
        self.assertAlmostEqual(sheet.fob_over_target, fob - 5.0, places=2)
        self.assertAlmostEqual(sheet.quoted_value, round(fob, 2) * 2000, places=2)
        self.assertAlmostEqual(sheet.material_share_pct, 1.4575 / fob * 100, places=1)
        # the price is built from unrounded line costs, not from the 2-decimal subtotals
        self.assertAlmostEqual(sheet._cost_parts()["total"], total, places=6)

    def test_buyer_supplied_fabric_is_left_out_of_the_price(self):
        sheet = self._sheet(buyer_supplies_fabric=True)
        self.assertEqual(sheet.fabric_cost_pc, 0.0)
        self.assertAlmostEqual(sheet.material_cost_pc, 0.04, places=4)

    def test_below_floor_flag_follows_margin_against_company_floor(self):
        self.assertFalse(self._sheet(margin_pct=12.0).below_floor)
        self.assertTrue(self._sheet(margin_pct=11.99).below_floor)

    def test_shares_of_fob_must_stay_under_one_hundred_percent(self):
        with self.assertRaises(ValidationError):
            self._sheet(overhead_pct=40.0, commission_pct=10.0, margin_pct=50.0)

    def test_line_efficiency_must_be_positive_percent(self):
        with self.assertRaises(ValidationError):
            self._sheet(line_efficiency=0.0)

    def test_what_if_shows_new_fob_without_changing_the_sheet(self):
        sheet = self._sheet(margin_pct=15.0)
        wiz = self.env["garment.cost.sheet.whatif"].with_context(default_sheet_id=sheet.id).create({})
        self.assertAlmostEqual(wiz.fob_price, sheet.fob_price, places=2)
        wiz.margin_pct = 20.0
        expected = sheet._cost_parts()["total"] / (1 - 0.23)
        self.assertAlmostEqual(wiz.fob_price, expected, places=2)
        self.assertEqual(sheet.margin_pct, 15.0)
        wiz.action_apply()
        self.assertEqual(sheet.margin_pct, 20.0)
