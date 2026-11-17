from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCockpit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Cockpit = cls.env["garment.cockpit"]
        cls.today = fields.Date.context_today(cls.Cockpit)

    def _tiles(self, key):
        return {t["key"]: t for t in self.Cockpit.get_cockpit(key)["tiles"]}

    def test_every_cockpit_returns_tiles_that_click_through_to_a_model(self):
        for c in self.Cockpit.get_cockpit_list():
            data = self.Cockpit.get_cockpit(c["key"])
            self.assertTrue(data["tiles"], c["key"])
            for tile in data["tiles"]:
                self.assertIn(tile["model"], self.env, (c["key"], tile["key"]))
                # the click-through domain must be a valid search on the tile's model
                self.env[tile["model"]].search_count(tile["domain"])

    def test_pulse_open_orders_are_confirmed_in_production_or_packed(self):
        tiles = self._tiles("pulse")
        dom = [("state", "in", ("confirmed", "in_production", "packed"))]
        orders = self.env["garment.order"].search(dom)
        self.assertEqual(tiles["orders_open"]["value"], len(orders))
        self.assertEqual(tiles["pieces"]["value"], sum(orders.mapped("qty_ordered")))

    def test_pulse_late_order_is_open_and_past_its_ex_factory_date(self):
        before = self._tiles("pulse")["late"]["value"]
        order = self.env["garment.order"].search(
            [("state", "in", ("confirmed", "in_production", "packed")),
             ("ex_factory_date", ">=", self.today)], limit=1)
        if not order:
            self.skipTest("no open order on time in demo data")
        order.ex_factory_date = self.today - timedelta(days=3)
        data = self.Cockpit.get_cockpit("pulse")
        self.assertEqual({t["key"]: t for t in data["tiles"]}["late"]["value"], before + 1)
        late_rows = {r["id"]: r for r in data["lists"][1]["rows"]}
        self.assertEqual(late_rows[order.id]["days_late"], 3)

    def test_pulse_pieces_by_stage_sums_the_order_quantities(self):
        chart = self.Cockpit.get_cockpit("pulse")["charts"][0]
        orders = self.env["garment.order"].search([("state", "in", ("confirmed", "in_production", "packed"))])
        self.assertEqual(chart["values"][0], sum(orders.mapped("qty_ordered")))
        self.assertEqual(chart["values"][2], sum(orders.mapped("qty_sewn")))

    def test_sewing_floor_output_is_the_sum_of_the_line_boards(self):
        data = self.Cockpit.get_cockpit("sewing")
        lines = self.env["garment.line"].search([])
        expected = sum(line._garment_hourly_board()["output"] for line in lines)
        self.assertEqual({t["key"]: t for t in data["tiles"]}["output"]["value"], expected)
        rows = data["lists"][-1]["rows"]
        if rows:
            behind = min(rows, key=lambda r: r["pct"])
            self.assertEqual(data["headline"]["behind"], behind["line"])

    def test_samples_tiles_count_by_state(self):
        tiles = self._tiles("samples")
        self.assertEqual(tiles["s_buyer"]["value"],
                         self.env["garment.sample"].search_count([("state", "=", "with_buyer")]))
        self.assertEqual(tiles["a_ok"]["value"],
                         self.env["garment.approval"].search_count([("state", "=", "approved")]))

    def test_tna_tiles_add_up_to_all_milestones(self):
        tiles = self._tiles("tna")
        self.assertEqual(sum(t["value"] for t in tiles.values()),
                         self.env["garment.tna.milestone"].search_count([]))

    def test_shipping_cartons_waiting_are_packed_not_shipped(self):
        self.assertEqual(self._tiles("shipping")["packed"]["value"],
                         self.env["garment.carton"].search_count([("state", "=", "packed")]))

    def test_quality_failed_finals_counts_final_inspections_that_failed(self):
        self.assertEqual(self._tiles("quality")["failed_finals"]["value"],
                         self.env["garment.inspection"].search_count([("kind", "=", "final"), ("result", "=", "fail")]))

    def test_jobwork_pending_pieces_of_orders_out(self):
        jobs = self.env["garment.jobwork.order"].search([("state", "in", ("sent", "partly_received"))])
        self.assertEqual(self._tiles("jobwork")["pending"]["value"], sum(jobs.mapped("qty_pending")))

    def test_profit_uses_the_pnl_summary(self):
        s = self.env["garment.order.pnl"]._garment_profit_summary()
        tiles = self._tiles("profit")
        self.assertEqual(tiles["revenue"]["value"], s["revenue"])
        self.assertEqual(tiles["loss"]["value"], s["loss_count"])

    def test_unknown_cockpit_is_refused(self):
        with self.assertRaises(Exception):
            self.Cockpit.get_cockpit("nope")

    def test_sewing_lines_stopped_now_are_lines_with_downtime_on_an_open_day(self):
        line = self.env["garment.line"].search([], limit=1)
        if not line:
            self.skipTest("no sewing line in demo data")
        day = self.env["garment.line.day"].search([("line_id", "=", line.id), ("date", "=", self.today)], limit=1) \
            or self.env["garment.line.day"].create({"line_id": line.id, "date": self.today})
        day.state = "open"
        before = self._tiles("sewing")
        self.env["garment.line.day.downtime"].create({"day_id": day.id, "reason": "Bottleneck: collar attach",
                                                      "minutes": 64})
        data = self.Cockpit.get_cockpit("sewing")
        tiles = {t["key"]: t for t in data["tiles"]}
        self.assertGreaterEqual(tiles["stopped"]["value"], 1)
        self.assertEqual(tiles["machines_down"]["value"], before["machines_down"]["value"])
        stopped = {r["reason"]: r for r in data["lists"][0]["rows"]}
        self.assertEqual(stopped["Bottleneck: collar attach"]["minutes"], 64)

    def test_pulse_filter_by_buyer_counts_only_that_buyers_orders(self):
        order = self.env["garment.order"].search([("state", "in", ("confirmed", "in_production", "packed"))], limit=1)
        if not order:
            self.skipTest("no open order")
        data = self.Cockpit.get_cockpit("pulse", {"buyer_id": order.buyer_id.id, "days": 7})
        tiles = {t["key"]: t for t in data["tiles"]}
        self.assertEqual(tiles["orders_open"]["value"], self.env["garment.order"].search_count(
            [("state", "in", ("confirmed", "in_production", "packed")), ("buyer_id", "=", order.buyer_id.id)]))
        self.assertEqual(len(data["charts"][1]["values"]), 7)
