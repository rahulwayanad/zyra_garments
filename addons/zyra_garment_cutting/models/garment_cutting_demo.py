"""Demo loader for cutting: markers, rolls, cut plans with lays for the late tee order (all three colourways
cut), bundles in every stage with scanned coupons, and draft/approved plans for two running orders.
Invented names only; dates relative to the install day."""
from datetime import timedelta

from odoo import api, fields, models

B = "zyra_garment_base."
T = "zyra_techpack."
M = "zyra_garment_merch."
C = "zyra_garment_cutting."

SHADES = ["A", "A", "B", "A", "B", "C", "A", "B", "B", "C", "A", "A", "B", "C", "A", "B", "A", "C", "B", "A"]


class GarmentCuttingDemo(models.AbstractModel):
    _name = "garment.cutting.demo"
    _description = "Cutting demo loader"

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _xmlid(self, record, name):
        self.env["ir.model.data"]._update_xmlids([{"xml_id": C + name, "record": record, "noupdate": True}])

    # ------------------------------------------------------------------
    def _markers(self, style, prefix, metres_per_piece, multi, fabric):
        """Markers of ``style``: the multi-size markers given in ``multi`` [(name, {size_name: ratio}, eff)]
        plus one single-size marker per size, so every plan can be covered exactly."""
        Marker = self.env["garment.marker"]
        sizes = {s.name: s for s in style.size_range_id.size_ids}
        markers = Marker
        for name, ratios, eff in multi:
            pieces = sum(ratios.values())
            markers |= Marker.create({
                "name": name, "style_id": style.id, "fabric_id": fabric.id, "width_cm": 180,
                "length_m": round(pieces * metres_per_piece * 0.97, 3), "efficiency_pct": eff,
                "line_ids": [(0, 0, {"size_id": sizes[n].id, "ratio": r}) for n, r in ratios.items()],
            })
        for i, size in enumerate(style.size_range_id.size_ids.sorted("sequence")):
            markers |= Marker.create({
                "name": "%s-%s" % (prefix, size.name), "sequence": 50 + i, "style_id": style.id,
                "fabric_id": fabric.id, "width_cm": 180, "length_m": round(metres_per_piece, 3),
                "efficiency_pct": 74.5 + i * 0.4,
                "line_ids": [(0, 0, {"size_id": size.id, "ratio": 1})],
            })
        return markers

    def _rolls(self, fabric, first_no, count, metres):
        Lot = self.env["stock.lot"]
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        rolls = Lot
        for i in range(count):
            name = "R%05d" % (first_no + i)
            lot = Lot.search([("name", "=", name), ("product_id", "=", fabric.id)], limit=1)
            if not lot:
                lot = Lot.create({
                    "name": name, "product_id": fabric.id, "company_id": self.env.company.id,
                    "is_fabric_roll": True, "roll_status": "approved", "dye_lot": "DL-%d" % (5100 + i // 4),
                    "shade_group": SHADES[i % len(SHADES)], "shrinkage_group": "S1", "width_cm": 182,
                    "gsm": 178 + i % 4, "points_per_100sqyd": 8.0 + (i % 5) * 3.1,
                })
                self.env["stock.quant"].sudo()._update_available_quantity(
                    fabric, warehouse.lot_stock_id, metres, lot_id=lot)
            rolls |= lot
        return rolls

    def _spread(self, lay, pool, spreader, cutter, table):
        """Spread ``lay`` from the roll pool (list of [lot, metres left]); ply counts follow the metres."""
        per_ply = lay.lay_length + lay.end_allowance_m
        plies_left = lay.plies_planned
        lines = []
        seq = 10
        while plies_left > 0 and pool:
            lot, left = pool[0]
            plies = min(plies_left, int(left // per_ply))
            if plies <= 0:
                pool.pop(0)
                continue
            lines.append((0, 0, {"sequence": seq, "lot_id": lot.id, "plies": plies}))
            seq += 10
            pool[0][1] = left - plies * per_ply
            plies_left -= plies
        lay.write({"roll_line_ids": lines, "spreader_id": spreader.id, "cutter_id": cutter.id, "table_name": table})

    # ------------------------------------------------------------------
    @api.model
    def _load_demo(self):
        if self._ref(C + "cut_plan_tee_navy"):
            return True
        order = self._ref(M + "order_tee_late")
        tee = self._ref(T + "style_crew_tee")
        polo = self._ref(T + "style_polo")
        chino = self._ref(T + "style_chino")
        jersey = self._ref(B + "product_fabric_jersey")
        twill = self._ref(T + "product_fabric_twill")
        if not (order and tee and polo and chino and jersey):
            return True
        today = fields.Date.context_today(self)
        now = fields.Datetime.now()
        planner = self._ref(B + "user_arjun") or self.env.user
        emp = {key: self._ref(C + "employee_" + key) for key in (
            "spreader_sunil", "spreader_ravi", "cutter_noushad", "cutter_deepa",
            "op_lina", "op_fathima", "op_ajmal", "op_jijo", "op_meera", "op_salim")}
        operators = [emp["op_lina"], emp["op_fathima"], emp["op_ajmal"], emp["op_jijo"], emp["op_meera"],
                     emp["op_salim"]]

        # Markers
        tee_markers = self._markers(tee, "TS", 1.12, [
            ("TS-A", {"S": 1, "M": 1, "L": 2, "XL": 2}, 82.4),
            ("TS-B", {"M": 1, "L": 1, "XL": 1}, 80.1),
        ], jersey)
        self._xmlid(tee_markers.filtered(lambda m: m.name == "TS-A"), "marker_tee_a")
        self._markers(polo, "PL", 1.22, [
            ("PL-A", {"XS": 1, "S": 1, "M": 2, "L": 2, "XL": 1, "XXL": 1}, 83.0),
            ("PL-B", {"M": 1, "L": 1}, 79.6),
        ], jersey)
        if twill:
            self._markers(chino, "CH", 1.31, [("CH-A", {"S": 1, "M": 2, "L": 2, "XL": 1}, 85.2)], twill)

        # Rolls in stock (approved, mixed shades)
        rolls = self._rolls(jersey, 961, 20, 420.0)
        pool = [[lot, 420.0] for lot in rolls]

        # The late tee order: its cut pieces come from the lays below, not from the merch demo postings.
        self.env["garment.order.progress"].sudo().search(
            [("order_id", "=", order.id), ("stage", "=", "cut")]).unlink()

        Plan = self.env["garment.cut.plan"]
        line2 = self._ref(M + "workcenter_line_2")
        colours = [(self._ref(B + "colour_navy"), "navy", 44), (self._ref(B + "colour_white"), "white", 38),
                   (self._ref(B + "colour_black"), "black", 30)]
        for c_index, (colour, key, days_ago) in enumerate(colours):
            plan = Plan.create({
                "order_id": order.id, "colour_id": colour.id, "planner_id": planner.id,
                "date_plan": today - timedelta(days=days_ago),
            })
            self._xmlid(plan, "cut_plan_tee_" + key)
            plan.action_propose()
            plan.action_approve()
            lays = plan.lay_ids.sorted("lay_no")
            for l_index, lay in enumerate(lays):
                spreader = emp["spreader_sunil"] if l_index % 2 == 0 else emp["spreader_ravi"]
                cutter = emp["cutter_noushad"] if l_index % 2 == 0 else emp["cutter_deepa"]
                self._spread(lay, pool, spreader, cutter, "Table %d" % (1 + (l_index + c_index) % 4))
                lay.lay_date = today - timedelta(days=days_ago - 1 - l_index)
                lay.action_spread()
                lay.action_cut()
                lay.cut_date = lay.lay_date
                # Black: the last two lays are cut but still on the table waiting for bundling.
                if key == "black" and l_index >= len(lays) - 2:
                    continue
                lay.action_create_bundles()
            if key == "navy":
                lays[:1].end_bits_m = 3.4
            self._bundle_stages(plan, key, line2, operators, now)

        # Polo: navy approved (first lay spread), black draft with proposals. Chino: draft.
        polo_order = self._ref(M + "order_polo_running")
        if polo_order:
            navy = Plan.create({"order_id": polo_order.id, "colour_id": self._ref(B + "colour_navy").id,
                                "planner_id": planner.id, "date_plan": today - timedelta(days=2)})
            navy.action_propose()
            navy.action_approve()
            first = navy.lay_ids.sorted("lay_no")[:1]
            self._spread(first, pool, emp["spreader_sunil"], emp["cutter_noushad"], "Table 2")
            first.action_spread()
            black = Plan.create({"order_id": polo_order.id, "colour_id": self._ref(B + "colour_black").id,
                                 "planner_id": planner.id, "date_plan": today - timedelta(days=1)})
            black.action_propose()
            self._xmlid(black, "cut_plan_polo_black")
        chino_order = self._ref(M + "order_chino_running")
        if chino_order and twill:
            plan = Plan.create({"order_id": chino_order.id, "colour_id": self._ref(B + "colour_black").id,
                                "planner_id": planner.id, "date_plan": today, "extra_cut_pct": 2.0})
            if plan._proposal_lines():
                plan.action_propose()
        return True

    def _bundle_stages(self, plan, key, line, operators, now):
        """Move the plan's bundles through the stages so the board shows every column."""
        bundles = plan.lay_ids.mapped("bundle_ids").sorted("id")
        if not bundles:
            return
        total = len(bundles)
        if key == "navy":
            issued, sewn, finished = bundles, bundles, bundles[: int(total * 0.8)]
        elif key == "white":
            issued = bundles[: int(total * 0.85)]
            sewn = bundles[: int(total * 0.3)]
            finished = bundles[: int(total * 0.1)]
        else:
            issued = bundles[: int(total * 0.25)]
            sewn = finished = bundles.browse()
        if issued:
            issued.action_issue(line, now - timedelta(days=6))
        in_sewing = issued[len(sewn): len(sewn) + max(int(len(issued) * 0.5) - len(sewn), 3)] \
            if key == "white" else bundles.browse()
        for b_index, bundle in enumerate(sewn | in_sewing):
            coupons = bundle.coupon_ids.sorted("sequence")
            stop = len(coupons) if bundle in sewn else (3 + b_index * 5) % max(len(coupons) - 1, 1) + 1
            start = now - timedelta(days=5 - b_index % 4, hours=6)
            for c_index, coupon in enumerate(coupons[:stop]):
                rejected = 1 if (b_index % 7 == 3 and c_index == 4) else 0
                coupon._garment_record_scan(
                    operators[c_index % len(operators)], rejected=rejected,
                    scanned_at=start + timedelta(minutes=27 * c_index),
                    reason="Open seam" if rejected else None)
        finished.action_finish()
