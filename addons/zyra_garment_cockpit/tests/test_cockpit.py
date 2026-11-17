from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "zyra")
class TestCockpit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Cockpit = cls.env["garment.cockpit"]
        cls.today = fields.Date.context_today(cls.Cockpit)

    def _panel(self, data, key):
        return next(p for p in data["panels"] if p["key"] == key)

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
        late_rows = {r["id"]: r for r in self._panel(data, "late")["rows"]}
        self.assertEqual(late_rows[order.id]["cells"][3], 3)

    def test_pulse_pieces_by_stage_sums_the_order_quantities(self):
        values = self._panel(self.Cockpit.get_cockpit("pulse"), "stage")["series"][0]["values"]
        orders = self.env["garment.order"].search([("state", "in", ("confirmed", "in_production", "packed"))])
        self.assertEqual(values[0], sum(orders.mapped("qty_ordered")))
        self.assertEqual(values[2], sum(orders.mapped("qty_sewn")))

    def test_sewing_floor_output_is_the_sum_of_the_line_boards(self):
        data = self.Cockpit.get_cockpit("sewing")
        lines = self.env["garment.line"].search([])
        expected = sum(line._garment_hourly_board()["output"] for line in lines)
        self.assertEqual({t["key"]: t for t in data["tiles"]}["output"]["value"], expected)
        rows = data["line_rows"]
        if rows:
            behind = min(rows, key=lambda r: r["pct"])
            self.assertEqual(data["headline_data"]["behind"], behind["line"])

    def test_samples_with_the_buyer_are_samples_in_state_with_buyer(self):
        tiles = self._tiles("samples")
        self.assertEqual(tiles["s_buyer"]["value"],
                         self.env["garment.sample"].search_count([("state", "=", "with_buyer")]))
        self.assertEqual(tiles["s_late"]["value"], len(self.env["garment.sample"].search(
            [("state", "not in", ("approved", "rejected"))]).filtered("is_overdue")))

    def test_tna_open_milestones_have_no_actual_date_and_overdue_are_among_them(self):
        tiles = self._tiles("tna")
        ms = self.env["garment.tna.milestone"].search([])
        self.assertEqual(tiles["open"]["value"], len(ms.filtered(lambda m: not m.actual_date)))
        self.assertEqual(tiles["overdue"]["value"],
                         len(ms.filtered(lambda m: not m.actual_date and m.status == "overdue")))

    def test_shipping_cartons_ready_are_packed_not_shipped(self):
        self.assertEqual(self._tiles("shipping")["packed"]["value"],
                         self.env["garment.carton"].search_count([("state", "=", "packed")]))

    def test_pulse_failed_finals_counts_final_inspections_with_result_failed(self):
        n = self.env["garment.inspection"].search_count([("kind", "=", "final"), ("result", "=", "failed")])
        self.assertEqual(self._tiles("pulse")["failed_finals"]["value"], n)
        insp = self.env["garment.inspection"].search([("kind", "=", "final"), ("result", "!=", "failed")], limit=1)
        if insp:
            insp.result = "failed"
            self.assertEqual(self._tiles("pulse")["failed_finals"]["value"], n + 1)

    def test_quality_finals_blocking_are_open_orders_whose_final_failed(self):
        self.assertEqual(self._tiles("quality")["blocking"]["value"], self.env["garment.order"].search_count(
            [("final_inspection_state", "=", "failed"), ("state", "not in", ("shipped", "closed", "cancel"))]))

    def test_jobwork_pending_pieces_of_orders_out(self):
        jobs = self.env["garment.jobwork.order"].search([("state", "in", ("sent", "partly_received"))])
        self.assertEqual(self._tiles("jobwork")["pending"]["value"], sum(jobs.mapped("qty_pending")))

    def test_profit_uses_the_pnl_summary_of_closed_orders_in_the_last_90_days(self):
        s = self.env["garment.order.pnl"]._garment_profit_summary(
            [("is_closed", "=", True), ("date_ex_factory", ">=", self.today - timedelta(days=89))])
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
        stopped = {r["cells"][1]: r for r in self._panel(data, "stopped")["rows"]}
        self.assertEqual(stopped["Bottleneck: collar attach"]["cells"][3], 64)

    def test_pulse_filter_by_buyer_counts_only_that_buyers_orders(self):
        order = self.env["garment.order"].search([("state", "in", ("confirmed", "in_production", "packed"))], limit=1)
        if not order:
            self.skipTest("no open order")
        data = self.Cockpit.get_cockpit("pulse", {"buyer_id": order.buyer_id.id, "days": 7})
        tiles = {t["key"]: t for t in data["tiles"]}
        self.assertEqual(tiles["orders_open"]["value"], self.env["garment.order"].search_count(
            [("state", "in", ("confirmed", "in_production", "packed")), ("buyer_id", "=", order.buyer_id.id)]))
        self.assertEqual(len(self._panel(data, "output")["series"][0]["values"]), 7)

    def test_every_cockpit_has_a_subtitle_a_headline_and_two_or_more_panels(self):
        for c in self.Cockpit.get_cockpit_list():
            data = self.Cockpit.get_cockpit(c["key"])
            self.assertTrue(data["subtitle"], c["key"])
            self.assertTrue(data["headline"], c["key"])
            self.assertGreaterEqual(len(data["panels"]), 2, c["key"])
            for panel in data["panels"]:
                self.assertIn(panel["type"], ("chart", "donut", "hbars", "table"), c["key"])
                if panel["type"] == "chart":
                    for s in panel["series"]:
                        self.assertEqual(len(s["values"]), len(panel["labels"]), (c["key"], panel["key"]))

    def test_every_filter_keeps_every_cockpit_working(self):
        order = self.env["garment.order"].search([], limit=1)
        for flt in ({"days": 7}, {"days": 90}, {"days": 365}, {"buyer_id": order.buyer_id.id},
                    {"business_model": "cmt"}):
            for c in self.Cockpit.get_cockpit_list():
                data = self.Cockpit.get_cockpit(c["key"], flt)
                for tile in data["tiles"]:
                    self.env[tile["model"]].search_count(tile["domain"])

    def test_orders_buyer_filter_counts_only_that_buyers_open_orders(self):
        order = self.env["garment.order"].search([("state", "in", ("confirmed", "in_production", "packed"))], limit=1)
        if not order:
            self.skipTest("no open order")
        data = self.Cockpit.get_cockpit("orders", {"buyer_id": order.buyer_id.id})
        self.assertEqual({t["key"]: t for t in data["tiles"]}["open"]["value"], self.env["garment.order"].search_count(
            [("state", "in", ("confirmed", "in_production", "packed")), ("buyer_id", "=", order.buyer_id.id)]))

    def test_orders_pieces_to_pack_never_counts_an_overpacked_order_against_another(self):
        late = self.env["garment.order"].search([("state", "in", ("confirmed", "in_production", "packed")),
                                                ("ex_factory_date", "<", self.today)])
        data = self.Cockpit.get_cockpit("orders")
        to_pack = sum(max(o.qty_ordered - o.qty_packed, 0) for o in late)
        self.assertIn("{:,}".format(to_pack), [p["t"] for p in data["headline"] if isinstance(p, dict)])

    def test_costing_under_floor_counts_approved_sheets_below_the_floor_in_12_months(self):
        dom = [("state", "=", "approved"), ("approved_date", ">=", self.today - timedelta(days=365)),
               ("below_floor", "=", True)]
        self.assertEqual(self._tiles("costing")["under"]["value"], self.env["garment.cost.sheet"].search_count(dom))

    def test_fabric_to_inspect_are_received_rolls_without_an_inspection(self):
        rolls = self.env["stock.lot"].search([("roll_status", "=", "received")])
        self.assertEqual(self._tiles("fabric")["to_inspect"]["value"],
                         len(rolls.filtered(lambda r: not r.roll_inspection_count)))

    def test_fabric_donut_adds_up_to_rolls_on_hand(self):
        data = self.Cockpit.get_cockpit("fabric")
        self.assertEqual(self._panel(data, "status")["total"], {t["key"]: t for t in data["tiles"]}["on_hand"]["value"])

    def test_cutting_cut_vs_plan_is_pieces_cut_over_pieces_to_cut(self):
        plans = self.env["garment.cut.plan"].search([("state", "not in", ("draft", "cancel"))])
        to_cut = sum(plans.mapped("qty_to_cut"))
        if not to_cut:
            self.skipTest("no cut plan")
        self.assertEqual(self._tiles("cutting")["vs_plan"]["value"],
                         round(sum(plans.mapped("qty_cut")) * 100.0 / to_cut))

    def test_capacity_booked_percent_is_booked_minutes_over_line_capacity(self):
        tiles = self._tiles("capacity")
        if not tiles["capacity"]["value"]:
            self.skipTest("no line capacity")
        self.assertEqual(tiles["pct"]["value"],
                         round(tiles["booked"]["value"] * 100.0 / tiles["capacity"]["value"]))

    def test_jobwork_late_returns_are_jobs_out_past_their_expected_date(self):
        jobs = self.env["garment.jobwork.order"].search([("state", "in", ("sent", "partly_received"))])
        self.assertEqual(self._tiles("jobwork")["late"]["value"],
                         len(jobs.filtered(lambda j: j.date_expected and j.date_expected < self.today)))

    def test_shipping_lc_expiring_is_open_and_expires_within_7_days(self):
        lc = self.env["garment.lc"].search([("state", "=", "open")], limit=1)
        if not lc:
            self.skipTest("no open LC")
        before = self._tiles("shipping")["lcs"]["value"]
        was_counted = self.today <= (lc.expiry_date or self.today - timedelta(days=1)) <= self.today + timedelta(days=7)
        lc.expiry_date = self.today + timedelta(days=3)
        self.assertEqual(self._tiles("shipping")["lcs"]["value"], before + (0 if was_counted else 1))

    def test_wages_gross_is_earnings_plus_topup_incentive_and_overtime_of_the_latest_week(self):
        latest = self.env["garment.wage.sheet"].search([("state", "!=", "cancel")], order="date_from desc", limit=1)
        if not latest:
            self.skipTest("no wage sheet")
        lines = self.env["garment.wage.sheet"].search(
            [("state", "!=", "cancel"), ("date_from", "=", latest.date_from)]).line_ids
        gross = sum(l.piece_earnings + l.topup + l.incentive + l.overtime_pay for l in lines)
        self.assertAlmostEqual(self._tiles("wages")["gross"]["value"], gross, places=2)

    def test_money_in_rupees_reads_as_lakh_when_short(self):
        inr = self.env.ref("base.INR")
        self.assertEqual(self.Cockpit._money(482310, currency=inr), "₹4.82 L")
        self.assertEqual(self.Cockpit._money(482310, short=False, currency=inr), "₹4,82,310")
        self.assertEqual(self.Cockpit._money(9140, currency=inr), "₹9,140")
