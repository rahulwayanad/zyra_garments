"""One full sale, end to end (demo only).

A new buyer (Coastline Outfitters) orders 1,100 organic crew tees in two colourways. The loader drives that one
order through every Zyra module with the modules' own buttons and APIs, so every figure on every screen comes
from a real document: tech pack → cost sheet → quotation → sale order → production order → samples, lab dip and
T&A → fabric booking, purchase, rolls and 4-point inspection → cut plan, lays and bundles → print job work →
sewing line, bulletin and coupon scans → inline / end-line / final AQL inspection → pack plan, cartons and stock →
letter of credit, shipment, customer invoice and payment → wage sheets → order P&L → order completed.

Dates run backwards from the install day (sale 80 days ago, paid today). Invented names only.
The walkthrough of the same story is in `.agents/docs/full-sale-walkthrough.md`.
"""
import base64
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.fields import Command
from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

B = "zyra_garment_base."
T = "zyra_techpack."
M = "zyra_garment_merch."
C = "zyra_garment_cutting."
S = "zyra_garment_suite."

# Pieces per colourway and size (S, M, L, XL)
GRID = {
    "sage": [100, 200, 250, 150],   # 700
    "white": [50, 100, 150, 100],   # 400
}
# (product, kind, placement, colour key or None, consumption, wastage %)
BOM = [
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "sage", 1.15, 5.0),
    (B + "product_fabric_jersey", "fabric", "Body, sleeves", "white", 1.15, 5.0),
    (T + "product_trim_neck_rib", "trim", "Neck", None, 0.48, 3.0),
    (T + "product_trim_neck_tape", "trim", "Back neck", None, 0.20, 3.0),
    (T + "product_trim_thread", "trim", "All seams", None, 0.03, 0.0),
    (T + "product_trim_main_label", "trim", "Centre back neck", None, 1.0, 0.0),
    (T + "product_trim_care_label", "trim", "Left side seam", None, 1.0, 0.0),
    (T + "product_trim_hangtag", "trim", "Left sleeve", None, 1.0, 0.0),
    (T + "product_pack_polybag", "packing", "", None, 1.0, 0.0),
]
# (pom code, base value, tol +, tol -, grade rule) on base size M
SPEC = [
    ("T04", 71.0, 1.5, 1.5, 2.0), ("T01", 52.0, 1.0, 0.5, 2.5), ("T03", 51.0, 1.0, 1.0, 2.5),
    ("T06", 45.0, 1.0, 1.0, 1.5), ("T11", 21.0, 0.5, 0.5, 0.5), ("T13", 19.5, 0.5, 0.5, 0.75),
    ("T15", 17.0, 0.5, 0.5, 0.5), ("T17", 18.0, 0.5, 0.5, 0.5), ("T18", 9.0, 0.5, 0.5, 0.25),
]
CONSTRUCTION = [
    ("Shoulder join", "514", 12, "superimposed", 0.7, "With stay tape"),
    ("Neck attach", "514", 12, "superimposed", 0.6, "Back neck tape, 301 topstitch"),
    ("Armhole", "514", 12, "superimposed", 0.7, ""),
    ("Side seam", "514", 12, "superimposed", 0.7, ""),
    ("Sleeve hem", "406", 12, "edge_finish", 2.0, "Twin needle"),
    ("Bottom hem", "406", 12, "edge_finish", 2.5, "Twin needle"),
]
OPERATORS = [  # (badge, name) — one operator per bulletin operation
    ("OP2101", "Reshma K"), ("OP2102", "Bindu Joseph"), ("OP2103", "Sabitha R"), ("OP2104", "Asha Mohan"),
    ("OP2105", "Nisha Paul"), ("OP2106", "Remya S"), ("OP2107", "Jincy Thomas"), ("OP2108", "Sreeja V"),
    ("OP2109", "Divya Babu"), ("OP2110", "Lekha N"), ("OP2111", "Soumya George"), ("OP2112", "Ambili Raj"),
]


class GarmentSuiteStoryDemo(models.AbstractModel):
    _name = "garment.suite.story.demo"
    _description = "Garment Suite demo: one full sale"

    # ------------------------------------------------------------------ helpers
    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _xmlid(self, record, name):
        self.env["ir.model.data"]._update_xmlids([{"xml_id": S + name, "record": record, "noupdate": True}])

    # state lives in the database (xml ids), not on the recordset
    @property
    def _today(self):
        return fields.Date.context_today(self)

    @property
    def _admin(self):
        return self.env.ref("base.user_admin")

    @property
    def _anjali(self):
        return self._ref(B + "user_anjali") or self._admin

    @property
    def _vivek(self):
        return self._ref(B + "user_vivek") or self._admin

    @property
    def _arjun(self):
        return self._ref(B + "user_arjun") or self._admin

    @property
    def _priya(self):
        return self._ref(B + "user_priya") or self._admin

    @property
    def _colours(self):
        return {"sage": self._ref(S + "story_colour_sage"), "white": self._ref(B + "colour_white")}

    @property
    def _buyer(self):
        return self._ref(S + "story_buyer")

    @property
    def _card(self):
        return self._ref(S + "story_rate_card")

    def _day(self, n):
        return self._today + timedelta(days=n)

    def _at(self, n, hour=10, minute=0):
        """Naive UTC datetime ``n`` days from today (negative = past) at hour:minute UTC."""
        return datetime.combine(self._day(n), time(hour, minute))

    def _note(self, record, body):
        record.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note")

    # ------------------------------------------------------------------ entry point
    @api.model
    def _load_demo(self):
        if self._ref(S + "story_order"):
            return True
        needed = [B + "partner_vendor_sunrise_prints", B + "product_fabric_jersey", B + "size_range_s_xl",
                  T + "product_trim_neck_rib", M + "tna_template_bulk", C + "employee_spreader_sunil",
                  "zyra_garment_wages.demo_rate_card"]
        if not all(self._ref(x) for x in needed):
            _logger.info("Full sale demo skipped: module demo data missing.")
            return True
        style, techpack = self._step_style()
        sheet = self._step_costing(techpack)
        sale = self._step_sale(style, sheet)
        order = sale.garment_order_ids[:1]
        self._xmlid(order, "story_order")
        self._step_development(order)
        bookings = self._step_materials(order)
        bundles = self._step_cutting(order, bookings)
        self._step_print(order, bundles)
        gline = self._step_sewing(order, style, techpack, bundles)
        self._step_quality_floor(order)
        plan = self._step_packing(order, bundles)
        shipment = self._step_shipping(order, plan)
        self._step_wages(gline)
        self._step_close(order, sale, shipment)
        return True

    # ------------------------------------------------------------------ 1. style and tech pack
    def _step_style(self):
        Colour = self.env["garment.colour"]
        sage = Colour.create({"name": "Sage", "code": "SGE", "pantone": "16-0213 TCX", "hex": "#9CAF88"})
        self._xmlid(sage, "story_colour_sage")
        buyer = self.env["res.partner"].create({
            "name": "Coastline Outfitters", "is_company": True, "is_garment_buyer": True, "buyer_code": "CLO",
            "street": "14 Harbour Row", "city": "Bristol", "zip": "BS1 5TY",
            "country_id": self.env.ref("base.uk").id, "email": "buying@coastline.example",
        })
        self._xmlid(buyer, "story_buyer")
        with file_open("zyra_techpack/static/img/sketch_tee.svg", "rb") as f:
            sketch = base64.b64encode(f.read())
        style = self.env["garment.style"].create({
            "code": "ST-0201", "name": "Organic Crew Tee", "buyer_id": buyer.id, "buyer_style_ref": "CLO-T-2207",
            "season_id": self._ref(B + "season_ss27").id, "collection": "SS27 · Organic Essentials",
            "type_id": self._ref(B + "garment_type_tshirt").id, "fabric_kind": "knit",
            "size_range_id": self._ref(B + "size_range_s_xl").id,
            "colour_ids": [Command.set([sage.id, self._colours["white"].id])],
            "merchandiser_id": self._anjali.id, "image_1920": sketch,
        })
        self._xmlid(style, "story_style")
        techpack = self.env["zyra.techpack"].create({
            "style_id": style.id, "base_size_id": self._ref(B + "size_s_xl_m").id,
            "change_note": "First issue from the buyer's brief CLO-T-2207.",
        })
        Pom = self.env["garment.pom"]
        ops = self.env["garment.operation"].search([("code", "=like", "TEE-%")], order="sequence, code")
        techpack.write({
            "measure_unit": "cm",
            "bom_line_ids": [Command.create({
                "sequence": i, "product_id": self._ref(p).id, "material_kind": kind, "placement": place or False,
                "colour_id": self._colours[col].id if col else False, "consumption": qty, "wastage_pct": waste,
            }) for i, (p, kind, place, col, qty, waste) in enumerate(BOM)],
            "measurement_ids": [Command.create({
                "sequence": i, "pom_id": Pom.search([("code", "=", code)], limit=1).id,
                "base_value": base, "tol_plus": plus, "tol_minus": minus, "grade_rule": grade,
            }) for i, (code, base, plus, minus, grade) in enumerate(SPEC)],
            "construction_ids": [Command.create({
                "sequence": i, "area": a, "stitch_class": st, "spi": spi, "seam_type": seam,
                "seam_allowance": al, "note": note or False,
            }) for i, (a, st, spi, seam, al, note) in enumerate(CONSTRUCTION)],
            "operation_ids": [Command.create({"sequence": i * 10, "operation_id": op.id})
                              for i, op in enumerate(ops, start=1)],
            "artwork_note": "<p>Chest print 'Coastline · Organic', water-based, 22 × 8 cm, 8 cm below neck.</p>",
            "label_note": "<p>Woven main label centre back; GOTS care label left side seam 8 cm above hem.</p>",
            "packing_note": "<p>Folded to 25 × 35 cm, one piece per polybag, 25 pieces per carton, "
                            "solid colour solid size.</p>",
        })
        self._xmlid(techpack, "story_techpack_v1")
        techpack.with_user(self._anjali).action_submit()
        techpack.with_user(self._admin).action_approve()
        if not style.product_tmpl_id:
            style.action_generate_variants_bom()
        techpack.sudo().write({"submitted_date": self._at(-96), "approved_date": self._at(-95)})
        self._note(style, "Enquiry from Coastline Outfitters (brief CLO-T-2207): 1,100 organic crew tees, two "
                          "colourways, target price USD 4.60 FOB. Tech pack v1 approved by the Factory Manager.")
        # Fit sample on the base size, measured against the graded spec, approved first round.
        sample = self.env["garment.sample"].create({
            "style_id": style.id, "sample_type": "fit", "colour_id": self._colours["sage"].id,
            "size_ids": [Command.set(self._ref(B + "size_s_xl_m").ids)],
            "size_measured_id": self._ref(B + "size_s_xl_m").id, "pieces": 2,
            "merchandiser_id": self._anjali.id, "request_date": self._day(-94), "required_date": self._day(-89),
            "cost": 38.0, "courier": "SwiftAir Couriers", "tracking_ref": "SA552019844",
        })
        self._xmlid(sample, "story_sample_fit")
        sample.action_start()
        sample.action_load_spec()
        for m, off in zip(sample.measurement_ids, [0.5, 0.0, -0.3, 0.4, 0.0, 0.2, -0.2, 0.0, 0.1]):
            m.measured = round(m.spec + off, 2)
        sample.sent_date = self._day(-90)
        sample.action_send_to_buyer()
        sample.buyer_comments = "Fit approved. Go ahead with costing."
        sample.decision_date = self._day(-87)
        sample.action_approve()
        return style, techpack

    # ------------------------------------------------------------------ 2. costing
    def _step_costing(self, techpack):
        sunrise = self._ref(B + "partner_vendor_sunrise_prints")
        sheet = self.env["garment.cost.sheet"].create({
            "techpack_id": techpack.id, "buyer_id": self._buyer.id, "costing_date": self._day(-86),
            "user_id": self._anjali.id, "quantity_basis": 1100, "target_price": 4.60, "freight_pc": 0.12,
            "overhead_pct": 3.0, "commission_pct": 0.0, "margin_pct": 14.0,
            "cost_per_minute": 0.0573, "line_efficiency": 62.0,
            "process_line_ids": [
                Command.create({"process_type": "print", "name": "Chest print, water-based", "charge_basis": "piece",
                                "cost": 0.18, "partner_id": sunrise.id}),
                Command.create({"process_type": "testing", "name": "GOTS and garment lab tests",
                                "charge_basis": "order", "cost": 150.0}),
                Command.create({"process_type": "packing", "name": "Folding, tagging and cartons",
                                "charge_basis": "piece", "cost": 0.06}),
            ],
        })
        sheet.action_submit()
        sheet.with_user(self._admin).action_approve()
        sheet.approved_date = self._day(-85)
        self._xmlid(sheet, "story_cost_sheet_v1")
        # First quotation at the v1 FOB (14 % margin): above the buyer's USD 4.60 target.
        sheet.action_create_quotation()
        first_quote = sheet.sale_order_ids[:1]
        first_quote.write({"client_order_ref": "CLO-T-2207 enquiry", "date_order": self._at(-85)})
        first_quote.action_quotation_sent()
        self._note(first_quote, "Buyer countered at USD 4.90 FOB for 1,100 pieces; quotation withdrawn and re-costed (v2).")
        first_quote._action_cancel()
        # v2: margin cut to 10 % to meet the counter. Under the 12 % floor, so only the Factory Manager can
        # approve it, with a reason that stays on the sheet and in the chatter.
        v2 = sheet.browse(sheet.with_user(self._admin).action_new_version()["res_id"])
        v2.write({"margin_pct": 10.0, "costing_date": self._day(-83)})
        v2.action_submit()
        v2.with_user(self._admin).with_context(garment_floor_reason=(
            "New buyer, first order: price agreed at the counter to open the account; repeat orders "
            "to be quoted at 14 %.")).action_approve()
        v2.approved_date = self._day(-82)
        self._xmlid(v2, "story_cost_sheet")
        return v2

    # ------------------------------------------------------------------ 3. quotation → sale order → production order
    def _step_sale(self, style, sheet):
        price = sheet.currency_id.round(sheet.fob_price)
        sizes = style.size_range_id.size_ids.sorted(lambda s: (s.sequence, s.id))
        lines = []
        for key, qtys in GRID.items():
            for size, qty in zip(sizes, qtys):
                variant = style._get_variant(self._colours[key], size)
                lines.append(Command.create({"product_id": variant.id, "product_uom_qty": qty, "price_unit": price}))
        sale = self.env["sale.order"].create({
            "partner_id": self._buyer.id, "client_order_ref": "CLO-PO-55120", "origin": sheet.display_name,
            "user_id": self._anjali.id, "date_order": self._at(-84),
            "commitment_date": self._at(-5), "incoterm": self._ref("account.incoterm_FOB").id,
            "order_line": lines,
        })
        sheet.sale_order_ids = [Command.link(sale.id)]
        self._xmlid(sale, "story_sale_order")
        sale.action_quotation_sent()
        sale.with_context(mail_notrack=True).action_confirm()
        sale.date_order = self._at(-80)
        order = sale.garment_order_ids[:1]
        order.write({
            "date_order": self._day(-80), "ex_factory_date": self._day(-5), "business_model": "fob",
            "merchandiser_id": self._anjali.id,
        })
        # the order was confirmed with the T&A of its real dates: re-plan the milestones on the dates above
        order.milestone_ids.unlink()
        order.action_apply_tna_template()
        self._note(order, "Opened from sale order %s (buyer PO CLO-PO-55120) at USD %.2f a piece, the FOB of "
                          "the approved cost sheet %s." % (sale.name, price, sheet.display_name))
        return sale

    # ------------------------------------------------------------------ 4. development: lab dip, trims, PP sample, T&A
    def _step_development(self, order):
        Approval = self.env["garment.approval"]
        dip = Approval.create({
            "style_id": order.style_id.id, "order_id": order.id, "kind": "lab_dip",
            "colour_id": self._colours["sage"].id, "material_id": self._ref(B + "product_fabric_jersey").id,
            "merchandiser_id": self._anjali.id, "courier": "SwiftAir Couriers", "decision_due": self._day(-70),
            "option_ids": [Command.create({"name": n, "hex": h, "sequence": i})
                           for i, (n, h) in enumerate([("A", "#97ab83"), ("B", "#9caf88"), ("C", "#a3b48f")])],
        })
        self._xmlid(dip, "story_labdip_sage")
        dip.action_send()
        dip.buyer_comment = "All three too yellow under D65; resubmit closer to the standard."
        dip.action_ask_resubmission()
        dip.action_send()
        dip.write({"first_sent_date": self._day(-78), "sent_date": self._day(-72)})
        dip.chosen_option_id = dip.option_ids.filtered(lambda o: o.name == "B")
        dip.buyer_comment = "Option B approved. Hold the shade within band A in bulk."
        dip.decision_date = self._day(-69)
        dip.action_approve()
        trims = Approval.create({
            "style_id": order.style_id.id, "order_id": order.id, "kind": "trim_card",
            "colour_id": self._colours["white"].id, "merchandiser_id": self._anjali.id,
            "decision_due": self._day(-66),
        })
        trims.action_send()
        trims.write({"first_sent_date": self._day(-72), "sent_date": self._day(-72), "decision_date": self._day(-67),
                     "buyer_comment": "Labels, hangtag and neck tape approved."})
        trims.action_approve()
        pp = self.env["garment.sample"].create({
            "style_id": order.style_id.id, "order_id": order.id, "sample_type": "pp",
            "colour_id": self._colours["sage"].id, "pieces": 2, "merchandiser_id": self._anjali.id,
            "size_ids": [Command.set(self._ref(B + "size_s_xl_m").ids)],
            "size_measured_id": self._ref(B + "size_s_xl_m").id,
            "request_date": self._day(-60), "required_date": self._day(-50), "cost": 46.0,
            "courier": "SwiftAir Couriers", "tracking_ref": "SA552077310",
        })
        self._xmlid(pp, "story_sample_pp")
        pp.action_start()
        pp.action_load_spec()
        for m, off in zip(pp.measurement_ids, [0.3, 0.2, 0.0, -0.4, 0.1, 0.0, 0.2, -0.1, 0.0]):
            m.measured = round(m.spec + off, 2)
        pp.sent_date = self._day(-52)
        pp.action_send_to_buyer()
        pp.buyer_comments = "Approved for bulk in bulk fabric and print. Keep the neck rib at 2 cm."
        pp.decision_date = self._day(-48)
        pp.action_approve()

    def _tna(self, order, upto, slips=None):
        """Mark milestones planned on or before ``upto`` days from today done (``slips``: name part → days late)."""
        slips = slips or {}
        for ms in order.milestone_ids.filtered(lambda m: not m.actual_date and m.planned_date <= self._day(upto)):
            late = next((d for k, d in slips.items() if k.lower() in ms.name.lower()), 0)
            ms.actual_date = ms.planned_date + timedelta(days=late)

    # ------------------------------------------------------------------ 5. materials
    def _step_materials(self, order):
        Demo = self.env["garment.materials.demo"]
        fabric = Demo._booking("story_booking_fabric_unused", order, confirm=True)
        trims = Demo._booking("story_booking_trims_unused", order, booking_of="trims", confirm=True)
        for booking, name in ((fabric, "story_booking_fabric"), (trims, "story_booking_trims")):
            self.env["ir.model.data"].search([("model", "=", "garment.fabric.booking"),
                                              ("res_id", "=", booking.id)]).unlink()
            self._xmlid(booking, name)
            booking.write({"booking_date": self._day(-76), "date_needed": self._day(-45)})
        rolls = Demo._receive(fabric, share=1.0, roll_size=160.0, received_days=-52)
        Demo._receive(trims, share=1.0, received_days=-50)
        for po in fabric._purchase_orders() | trims._purchase_orders():
            po.write({"date_order": self._at(-74), "date_approve": self._at(-74)})
        # 4-point inspection on every roll (a buyer requirement for organic jersey); all pass
        for i, roll in enumerate(rolls.sorted("name")):
            yards = roll._roll_length_yards()
            defects = Demo._spread(3 + i % 4, ["1", "2", "1", "3"], yards) if yards > 120 else []
            insp = Demo._inspect(roll, defects, days=-50 + i % 2)
            insp.inspector_id = self._vivek
        self._tna(order, -45, {"lab dip": 1})
        return fabric | trims

    # ------------------------------------------------------------------ 6. cutting
    def _step_cutting(self, order, bookings):
        CutDemo = self.env["garment.cutting.demo"]
        style = order.style_id
        jersey = self._ref(B + "product_fabric_jersey")
        CutDemo._markers(style, "CLO", 1.12, [
            ("CLO-A", {"S": 1, "M": 2, "L": 2, "XL": 1}, 83.1),
            ("CLO-B", {"L": 1, "XL": 1}, 80.4),
        ], jersey)
        emp = {k: self._ref(C + "employee_" + k) for k in
               ("spreader_sunil", "spreader_ravi", "cutter_noushad", "cutter_deepa")}
        rolls = bookings.roll_ids.filtered(lambda r: r.roll_status == "approved")
        bundles = self.env["garment.bundle"]
        for c_index, key in enumerate(("sage", "white")):
            colour = self._colours[key]
            plan = self.env["garment.cut.plan"].create({
                "order_id": order.id, "colour_id": colour.id, "planner_id": self._arjun.id,
                "date_plan": self._day(-42 + c_index), "bundle_size": 30, "extra_cut_pct": 2.0, "max_plies": 110,
            })
            self._xmlid(plan, "story_cut_plan_" + key)
            plan.action_propose()
            plan.action_approve()
            pool = [[lot, lot.product_qty] for lot in rolls.filtered(
                lambda r: r.booking_line_id.colour_id == colour).sorted("name")]
            for l_index, lay in enumerate(plan.lay_ids.sorted("lay_no")):
                spreader = emp["spreader_sunil"] if l_index % 2 == 0 else emp["spreader_ravi"]
                cutter = emp["cutter_noushad"] if l_index % 2 == 0 else emp["cutter_deepa"]
                CutDemo._spread(lay, pool, spreader, cutter, "Table %d" % (1 + l_index % 3))
                lay.bundle_size = 30
                lay.lay_date = self._day(-41 + c_index + l_index // 2)
                lay.action_spread()
                lay.action_cut()
                lay.cut_date = lay.lay_date
                lay.action_create_bundles()
            bundles |= plan.lay_ids.bundle_ids
        return bundles

    # ------------------------------------------------------------------ 7. print job work
    def _step_print(self, order, bundles):
        sunrise = self._ref(B + "partner_vendor_sunrise_prints")
        jw = self.env["garment.jobwork.order"].create({
            "vendor_id": sunrise.id, "process": "print", "production_order_id": order.id, "rate": 0.18,
            "allowance_pct": 1.0, "bundle_ids": [Command.set(bundles.ids)],
            "date_issue": self._day(-37), "date_expected": self._day(-32),
        })
        self._xmlid(jw, "story_jobwork_print")
        jw.action_send()
        sent = jw.qty_sent
        jw._garment_receive(int(sent * 0.55), 2, date=self._day(-34))
        jw._garment_receive(jw.qty_pending - 3, 3, date=self._day(-32))
        jw.action_bill()
        for po in jw.purchase_ids:
            po.write({"date_order": self._at(-32), "date_approve": self._at(-32)})
        self._note(jw, "Front panels printed and back: 5 rejected for print smudge (re-cut from end bits), "
                       "inside the 1 %% allowance. Billed at USD 0.18 on %s good pieces." % jw.qty_good)
        return jw

    # ------------------------------------------------------------------ 8. sewing
    def _step_sewing(self, order, style, techpack, bundles):
        Employee = self.env["hr.employee"]
        dept = self.env["hr.department"].create({"name": "Line 5 · Organic Knits"})
        operators = Employee.browse()
        for badge, name in OPERATORS:
            operators |= Employee.create({"name": name, "barcode": badge, "department_id": dept.id})
        supervisor = Employee.create({"name": "Manoj Kurian", "department_id": dept.id})
        gline = self.env["garment.line"].create({
            "name": "Line 5", "code": "L5", "supervisor_id": supervisor.id,
            "employee_ids": [Command.set(operators.ids)], "operator_count": len(operators),
            "machine_count": 14, "working_minutes": 480, "target_efficiency": 60.0,
        })
        self._xmlid(gline, "story_sewing_line")
        order.sewing_line_id = gline.workcenter_id
        bulletin = self.env["garment.bulletin"].create({
            "name": "Bulletin %s" % style.display_name, "style_id": style.id, "techpack_id": techpack.id})
        bulletin.action_load_from_techpack()
        bulletin.action_approve()
        gline.current_bulletin_id = bulletin
        # USD rate card of this line (the rupee card of the other demo lines stays as it is)
        card = self.env["garment.rate.card"].create({
            "name": "Line 5 · USD standard minute", "minute_value": 0.0573, "hours_per_day": 8,
            "min_daily_wage": 9.0, "topup_period": "weekly", "overtime_multiplier": 2,
            "incentive_threshold": 70, "incentive_percent": 10, "valid_from": self._day(-60),
        })
        card.action_activate()
        card.bulletin_ids = bulletin
        card.action_apply_to_bulletins()
        self._xmlid(card, "story_rate_card")

        # Issue every bundle to Line 5 and scan every coupon: one operator per operation, three working days.
        bundles = bundles.sorted("id")
        bundles.action_issue(gline.workcenter_id, self._at(-30, 3))
        op_owner = {}
        for i, op in enumerate(techpack.operation_ids.sorted("sequence")):
            op_owner[op.id] = operators[i % len(operators)]
        days = [d for d in range(-30, -16) if self._day(d).weekday() < 5][:3]
        Scan = self.env["garment.scan"]
        per_day = max(1, -(-len(bundles) // len(days)))
        for b_index, bundle in enumerate(bundles):
            day = days[min(b_index // per_day, len(days) - 1)]
            slot = b_index % per_day
            for c_index, coupon in enumerate(bundle.coupon_ids.sorted("sequence")):
                operator = op_owner.get(coupon.operation_id.id, operators[c_index % len(operators)])
                rejected = 1 if (b_index % 9 == 4 and c_index == 7) else 0
                Scan._garment_scan(coupon.payload, operator, line=gline,
                                   scanned_at=self._at(day, 3) + timedelta(minutes=25 * slot + 2 * c_index),
                                   rejected=rejected, reason="Open seam at side" if rejected else None)
        bundles.filtered(lambda b: b.stage == "sewn").action_finish()
        self._tna(order, -18, {"pp sample": 2})
        return gline

    # ------------------------------------------------------------------ 9. quality on the floor
    def _inspection(self, order, kind, when, pieces, defects, lot=None):
        lines = []
        for code, position, qty in defects:
            defect = self.env["garment.defect"].search([("code", "=", code)], limit=1)
            lines.append(Command.create({"defect_id": defect.id, "position": position, "qty": qty, "date": when}))
        vals = {"kind": kind, "order_id": order.id, "date": when, "pieces_checked": pieces,
                "inspector_id": self._priya.id, "defect_line_ids": lines}
        if lot:
            vals["lot_size"] = lot
        insp = self.env["garment.inspection"].create(vals)
        insp.action_complete()
        return insp

    def _step_quality_floor(self, order):
        self._inspection(order, "inline", self._at(-29, 6), 40, [("W02", "collar", 2), ("W04", "left_sleeve", 1)])
        self._inspection(order, "inline", self._at(-26, 6), 40, [("W10", "hem", 1)])
        self._inspection(order, "endline", self._at(-24, 9), 120, [("W01", "side_seams", 2), ("D05", False, 1)])
        self._inspection(order, "endline", self._at(-20, 9), 120, [("W10", "hem", 1)])

    # ------------------------------------------------------------------ 10. packing, final inspection, stock
    def _step_packing(self, order, bundles):
        plan = self.env["garment.pack.plan"].create({
            "order_id": order.id, "pack_kind": "solid", "pieces_per_carton": 25,
            "length_cm": 60, "width_cm": 40, "height_cm": 30,
            "net_weight_per_piece": 0.19, "empty_carton_weight": 0.9,
        })
        self._xmlid(plan, "story_pack_plan")
        plan.action_generate_cartons()
        plan.carton_ids.action_pack()
        plan.carton_ids.write({"date_packed": self._at(-10, 8)})
        final = self._inspection(order, "final", self._at(-8, 6), 80,
                                 [("W01", "side_seams", 2), ("W10", "hem", 1), ("D05", False, 2)],
                                 lot=order.qty_packed)
        self._xmlid(final, "story_final_inspection")
        plan.action_post_to_stock()
        # P&L reads material issued to the order through stock.move.garment_pnl_order_id; the finished-goods MOs
        # consume the trims and packing, so tag those moves (fabric was already costed when the lays were cut).
        plan.production_ids.move_raw_ids.filtered(
            lambda m: m.state == "done" and m.product_id.tracking == "none").write({"garment_pnl_order_id": order.id})
        self._tna(order, -8)
        return plan

    # ------------------------------------------------------------------ 11. shipping, invoice, payment
    def _step_shipping(self, order, plan):
        lc = self.env["garment.lc"].create({
            "name": "LCCLO71148", "buyer_id": self._buyer.id, "issuing_bank": "Severn Merchant Bank, Bristol",
            "advising_bank": "Coastal Commerce Bank, Kochi", "amount": round(order.order_value * 1.02, -2),
            "tolerance_pct": 5.0, "latest_shipment_date": self._day(-1), "expiry_date": self._day(20),
            "state": "open",
        })
        self._xmlid(lc, "story_lc")
        shipment = self.env["garment.shipment"].create({
            "buyer_id": self._buyer.id, "order_ids": [Command.set(order.ids)], "lc_id": lc.id,
            "planned_date": self._day(-5), "mode": "sea", "port_loading": "Kochi",
            "port_discharge": "Felixstowe", "forwarder": "Bluewater Logistics", "vessel_flight": "MV Arabian Tern",
            "transport_doc_no": "BWL-KOC-90417", "incoterm_id": self._ref("account.incoterm_FOB").id,
        })
        self._xmlid(shipment, "story_shipment")
        shipment.action_add_packed_cartons()
        shipment.action_confirm()
        shipment.actual_date = self._day(-5)
        shipment.action_ex_factory()
        shipment.action_handed_over()
        shipment.action_on_board()
        shipment.action_documents_presented()
        shipment.lc_id.drawing_ids.write({"date": self._day(-2)})
        shipment.action_create_invoice()
        invoice = shipment.invoice_ids[:1]
        invoice.write({"invoice_date": self._day(-3), "ref": "CLO-PO-55120"})
        invoice.invoice_line_ids.write({"garment_order_id": order.id, "tax_ids": [Command.clear()]})
        invoice.action_post()
        self._xmlid(invoice, "story_invoice")
        journal = self.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", invoice.company_id.id)], limit=1)
        self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids).create({
                "journal_id": journal.id, "payment_date": self._today,
                "communication": "LCCLO71148 proceeds"})._create_payments()
        shipment.action_paid()
        self._tna(order, 0)
        return shipment

    # ------------------------------------------------------------------ 12. wages
    def _step_wages(self, gline):
        Account = self.env["account.account"]
        expense = Account.search([("code", "=", "WAGEXP")], limit=1) or Account.create(
            {"name": "Wages Expense", "code": "WAGEXP", "account_type": "expense"})
        payable = Account.search([("code", "=", "WAGPAY")], limit=1) or Account.create(
            {"name": "Wages Payable", "code": "WAGPAY", "account_type": "liability_current"})
        journal = self.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", self.env.company.id)], limit=1)
        scan_days = sorted({s.scanned_at.date() for s in gline.scan_ids})
        weeks = sorted({d - timedelta(days=d.weekday()) for d in scan_days})
        for monday in weeks:
            sheet = self.env["garment.wage.sheet"].create({
                "rate_card_id": self._card.id, "journal_id": journal.id, "expense_account_id": expense.id,
                "payable_account_id": payable.id, "line_id": gline.id,
                "date_from": monday, "date_to": monday + timedelta(days=5),
            })
            sheet.action_compute()
            sheet.line_ids[:2].write({"overtime_hours": 1.5})
            sheet.action_compute()
            sheet.action_approve()
            sheet.action_post()

    # ------------------------------------------------------------------ 13. close the order
    def _step_close(self, order, sale, shipment):
        order.action_mark_completed()
        pnl = order._garment_pnl()
        pnl.cost_line_ids = [Command.create({
            "date": self._day(-5), "name": "Inland haulage to Kochi port and CHA fees", "amount": 96.0}),
            Command.create({"date": self._day(-40), "name": "GOTS certificate and garment lab tests",
                            "amount": 150.0}),
            Command.create({"date": self._day(-2), "name": "LC negotiation and courier of documents",
                            "amount": 38.5})]
        pnl.action_refresh()
        self._xmlid(pnl, "story_pnl")
        self._note(order, "Completed: %s pieces shipped on %s, invoiced and paid under %s. See the P&L for the "
                          "margin against plan." % (order.qty_shipped, shipment.name, shipment.lc_id.name))
