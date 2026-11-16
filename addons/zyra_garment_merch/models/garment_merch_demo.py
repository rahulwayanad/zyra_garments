"""Demo loader for merchandising: production orders (one late), progress postings, samples in every
stage, approval cards and T&A plans. Dates are relative to the day the demo is loaded so the late order
stays late and the board shows overdue cards."""
from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Command

B = "zyra_garment_base."
T = "zyra_techpack."
M = "zyra_garment_merch."

# Share of the ordered quantity per size (rough bell curve), indexed by size position.
SIZE_SPLIT = [0.11, 0.17, 0.22, 0.22, 0.17, 0.11]


class GarmentMerchDemo(models.AbstractModel):
    _name = "garment.merch.demo"
    _description = "Merchandising demo loader"

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _xmlid(self, record, name):
        self.env["ir.model.data"]._update_xmlids([{"xml_id": M + name, "record": record, "noupdate": True}])

    def _grid(self, order, pieces_per_colour):
        """Spread ``pieces_per_colour`` over the sizes of each colourway of ``order``."""
        sizes = order.size_ids.sorted(lambda s: (s.sequence, s.id))
        split = SIZE_SPLIT[:len(sizes)] if len(sizes) <= len(SIZE_SPLIT) else [1.0 / len(sizes)] * len(sizes)
        total = sum(split)
        for colour, pieces in pieces_per_colour.items():
            for size, share in zip(sizes, split):
                line = order.line_ids.filtered(lambda l: l.colour_id == colour and l.size_id == size)
                line.qty_ordered = int(round(pieces * share / total / 5.0) * 5)

    def _post(self, order, ratios, ref_prefix):
        """Post cut / sewn / packed / shipped as ratios of the ordered quantity, cell by cell."""
        for line in order.line_ids:
            for stage in ("cut", "sewn", "packed", "shipped"):
                ratio = ratios.get(stage, 0.0)
                qty = int(round(line.qty_ordered * ratio))
                if qty:
                    order._garment_add_progress(stage, line.colour_id.id, line.size_id.id, qty,
                                                ref="%s-%s" % (ref_prefix, stage.upper()))

    def _make_order(self, xmlid, style, buyer, ex_days, pieces_by_colour, line=None, price=0.0, po=None,
               order_days=-75, template=True):
        today = fields.Date.context_today(self)
        order = self.env["garment.order"].create({
            "style_id": style.id,
            "buyer_id": buyer.id,
            "buyer_po": po,
            "date_order": today + timedelta(days=order_days),
            "ex_factory_date": today + timedelta(days=ex_days),
            "sewing_line_id": line.id if line else False,
            "price_unit": price,
            "merchandiser_id": (self._ref(B + "user_anjali") or self.env.user).id,
            "tna_template_id": self._ref(M + "tna_template_bulk").id if template else False,
            "colour_ids": [Command.set(list(c.id for c in pieces_by_colour))],
        })
        self._grid(order, pieces_by_colour)
        self._xmlid(order, xmlid)
        return order

    def _confirm(self, order):
        """Demo confirm: the style's approval gate is checked by the real button; demo styles may be open."""
        if order.style_id.approved_for_production:
            order.action_confirm()
        else:
            order.state = "confirmed"
            if order.tna_template_id and not order.milestone_ids:
                order.action_apply_tna_template()

    def _tna_actuals(self, order, done_count, slips=None):
        """Mark the first ``done_count`` milestones done on plan (``slips`` {index: days late})."""
        slips = slips or {}
        for index, ms in enumerate(order.milestone_ids.sorted(lambda m: (m.planned_date, m.sequence))):
            if index < done_count:
                ms.actual_date = ms.planned_date + timedelta(days=slips.get(index, 0))

    @api.model
    def _load_demo(self):
        if self._ref(M + "order_tee_late"):
            return True
        tee = self._ref(T + "style_crew_tee")
        polo = self._ref(T + "style_polo")
        chino = self._ref(T + "style_chino")
        jean = self._ref(T + "style_jean")
        oxford = self._ref(T + "style_oxford")
        if not (tee and polo and chino and jean and oxford):
            return True  # tech pack demo not loaded
        northwind = self._ref(B + "partner_buyer_northwind")
        bluefin = self._ref(B + "partner_buyer_bluefin")
        maple = self._ref(B + "partner_buyer_maple")
        navy, white, black = (self._ref(B + "colour_navy"), self._ref(B + "colour_white"),
                              self._ref(B + "colour_black"))
        grey, indigo, sky = self._ref(B + "colour_grey"), self._ref(B + "colour_indigo"), self._ref(B + "colour_sky")
        line1, line2, line3, line4 = (self._ref(M + "workcenter_line_1"), self._ref(M + "workcenter_line_2"),
                                      self._ref(M + "workcenter_line_3"), self._ref(M + "workcenter_line_4"))
        today = fields.Date.context_today(self)

        # 1. The late order (screen 2): opened from a confirmed sale order, three days past ex-factory.
        order_late = self._order_from_sale(tee, northwind, {navy: 1450, white: 1890, black: 1690}, 7.23, "NW-427174")
        if not order_late:
            order_late = self._make_order("order_tee_late", tee, northwind, -3, {navy: 1450, white: 1890, black: 1690},
                                     line2, 7.23, "NW-427174", order_days=-90)
            self._confirm(order_late)
        else:
            self._xmlid(order_late, "order_tee_late")
            order_late.write({"date_order": today - timedelta(days=90), "ex_factory_date": today - timedelta(days=3),
                              "sewing_line_id": line2.id,
                              "merchandiser_id": (self._ref(B + "user_anjali") or self.env.user).id})
        order_late.action_start_production()
        self._post(order_late, {"cut": 1.03, "sewn": 1.01, "packed": 0.75, "shipped": 0.35}, "PO-TEE")
        self._tna_actuals(order_late, 7, {1: -1, 3: 1, 6: 1})

        # 2. Second late order: jean for Maple, two days past ex-factory, packing behind.
        order_jean = self._make_order("order_jean_late", jean, maple, -2, {indigo: 1880}, line4, 9.41, "MF-433498",
                                 order_days=-85)
        self._confirm(order_jean)
        self._post(order_jean, {"cut": 1.03, "sewn": 0.96, "packed": 0.41}, "PO-JEAN")
        self._tna_actuals(order_jean, 7)

        # 3. Polo for Maple, ex-factory in six days.
        order_polo = self._make_order("order_polo_running", polo, maple, 6, {navy: 900, black: 850}, line1, 4.59,
                                 "MF-444109", order_days=-70)
        self._confirm(order_polo)
        self._post(order_polo, {"cut": 1.03, "sewn": 0.81, "packed": 0.26}, "PO-POLO")
        self._tna_actuals(order_polo, 7, {5: 1})

        # 4. Chino for Bluefin, in its first week of production.
        order_chino = self._make_order("order_chino_running", chino, bluefin, 24, {black: 600, grey: 510}, line4, 5.92,
                                  "BF-497308", order_days=-45)
        self._confirm(order_chino)
        self._post(order_chino, {"cut": 0.62, "sewn": 0.27}, "PO-CHINO")
        self._tna_actuals(order_chino, 5)

        # 5. Second tee order for Northwind, confirmed, not started.
        order_tee2 = self._make_order("order_tee_confirmed", tee, northwind, 40, {navy: 1300, black: 960}, line2, 2.87,
                                 "NW-469291", order_days=-20)
        self._confirm(order_tee2)
        self._tna_actuals(order_tee2, 1)

        # 6. Oxford shirt (tech pack still in development): a draft order waiting for the approval.
        self._make_order("order_oxford_draft", oxford, northwind, 60, {sky: 1700, white: 1450}, line3, 7.96,
                    "NW-483591", order_days=-2)

        # 7. A polo order shipped last month and completed.
        order_done = self._make_order("order_polo_shipped", polo, bluefin, -30, {navy: 600}, line1, 4.40, "BF-412337",
                                 order_days=-120)
        self._confirm(order_done)
        self._post(order_done, {"cut": 1.02, "sewn": 1.01, "packed": 1.0, "shipped": 1.0}, "PO-POLO2")
        self._tna_actuals(order_done, 11)
        order_done.action_mark_completed()

        self._load_samples(order_late, order_polo, order_jean, order_chino, polo, tee, oxford, chino)
        self._load_approvals(tee, polo, chino, jean, oxford, order_late)
        order_late.message_post(body="Time and action: %s milestones now fall after the ex-factory date."
                                % order_late.milestone_overdue_count)
        return True

    def _order_from_sale(self, style, buyer, pieces_by_colour, price, po):
        """Confirm a sale order of the style's variants: the production order opens from it."""
        if not style.product_tmpl_id or not hasattr(style, "_get_variant"):
            return False
        sizes = style.size_range_id.size_ids.sorted(lambda s: (s.sequence, s.id))
        split = SIZE_SPLIT[:len(sizes)]
        lines = []
        for colour, pieces in pieces_by_colour.items():
            for size, share in zip(sizes, split):
                variant = style._get_variant(colour, size)
                if not variant:
                    return False
                lines.append(Command.create({
                    "product_id": variant.id,
                    "product_uom_qty": int(round(pieces * share / sum(split) / 5.0) * 5),
                    "price_unit": price,
                }))
        so = self.env["sale.order"].create({
            "partner_id": buyer.id,
            "client_order_ref": po,
            "commitment_date": fields.Datetime.now() + timedelta(days=30),
            "order_line": lines,
        })
        so.action_confirm()
        self.env["ir.model.data"]._update_xmlids([{"xml_id": M + "sale_order_tee", "record": so, "noupdate": True}])
        return so.garment_order_ids[:1]

    def _load_samples(self, order_late, order_polo, order_jean, order_chino, polo, tee, oxford, chino):
        today = fields.Date.context_today(self)
        Sample = self.env["garment.sample"]
        d = lambda n: today + timedelta(days=n)  # noqa: E731
        anjali = self._ref(B + "user_anjali") or self.env.user
        vals = [
            ("sample_oxford_proto", {"style_id": oxford.id, "sample_type": "proto", "colour_id": self._ref(B + "colour_white").id,
                                     "required_date": d(4), "pieces": 2}, "in_progress"),
            ("sample_chino_fit", {"style_id": chino.id, "sample_type": "fit", "colour_id": self._ref(B + "colour_black").id,
                                  "required_date": d(2), "pieces": 2}, "in_progress"),
            ("sample_tee_top", {"style_id": tee.id, "order_id": order_late.id, "sample_type": "top",
                                "colour_id": self._ref(B + "colour_white").id, "required_date": d(2), "pieces": 3},
             "in_progress"),
            ("sample_oxford_fit", {"style_id": oxford.id, "sample_type": "fit", "colour_id": self._ref(B + "colour_sky").id,
                                   "required_date": d(5), "pieces": 2}, "rejected"),
            ("sample_jean_pp", {"style_id": order_jean.style_id.id, "order_id": order_jean.id, "sample_type": "pp",
                                "colour_id": self._ref(B + "colour_indigo").id, "required_date": d(-9), "pieces": 2},
             "rejected"),
            ("sample_chino_pp", {"style_id": chino.id, "order_id": order_chino.id, "sample_type": "pp",
                                 "colour_id": self._ref(B + "colour_grey").id, "required_date": d(-6), "pieces": 2},
             "requested"),
            ("sample_polo_pp_req", {"style_id": polo.id, "sample_type": "salesman",
                                    "colour_id": self._ref(B + "colour_navy").id, "required_date": d(10), "pieces": 6},
             "requested"),
            ("sample_tee_shipment", {"style_id": tee.id, "order_id": order_late.id, "sample_type": "shipment",
                                     "colour_id": self._ref(B + "colour_navy").id, "required_date": d(3), "pieces": 3,
                                     "courier": "SwiftAir Couriers", "tracking_ref": "SA449120387"}, "with_buyer"),
            ("sample_polo_sms", {"style_id": polo.id, "sample_type": "salesman",
                                 "colour_id": self._ref(B + "colour_black").id, "required_date": d(3), "pieces": 12},
             "with_buyer"),
            ("sample_tee_pp", {"style_id": tee.id, "order_id": order_late.id, "sample_type": "pp",
                               "colour_id": self._ref(B + "colour_black").id, "required_date": d(-60), "pieces": 2,
                               "buyer_comments": "Approved for bulk. Keep the neck rib at 2 cm."}, "approved"),
            ("sample_polo_pp", {"style_id": polo.id, "order_id": order_polo.id, "sample_type": "pp",
                                "colour_id": self._ref(B + "colour_navy").id, "required_date": d(-40), "pieces": 2},
             "approved"),
        ]
        for xmlid, v, state in vals:
            v.setdefault("merchandiser_id", anjali.id)
            v.setdefault("request_date", (v.get("required_date") or today) - timedelta(days=14))
            sample = Sample.create(v)
            self._xmlid(sample, xmlid)
            if state == "requested":
                continue
            sample.action_start()
            if state == "in_progress":
                continue
            sample.sent_date = v["required_date"] - timedelta(days=4)
            sample.action_send_to_buyer()
            if state == "with_buyer":
                continue
            sample.decision_date = v["required_date"] + timedelta(days=3)
            if state == "rejected":
                sample.buyer_comments = "Waist too tight; shorten the body by 1 cm and resubmit."
                sample.action_reject()
                if xmlid == "sample_oxford_fit":
                    # a second round, rejected again: the card shows "round 2"
                    sample.action_remake()
                    sample.action_send_to_buyer()
                    sample.buyer_comments = "Collar points still uneven; remake with a firmer interlining."
                    sample.action_reject()
            else:
                sample.action_approve()
        if order_late.pp_sample_ok:
            order_late.message_post(body="Pre-production sample %s approved in round 1."
                                    % self._ref(M + "sample_tee_pp").name)

        # Size set sample with the fit measurements (screens 27–28).
        size_xl = self._ref(B + "size_xs_xxl_xl")
        sizes = polo.size_range_id.size_ids
        size_set = Sample.create({
            "style_id": polo.id, "order_id": order_polo.id, "sample_type": "size_set",
            "colour_id": self._ref(B + "colour_navy").id, "size_ids": [Command.set(sizes.ids)],
            "pieces": len(sizes), "size_measured_id": size_xl.id if size_xl else False,
            "request_date": d(-75), "required_date": d(-61), "cost": 162.68, "courier": "SwiftAir Couriers",
            "tracking_ref": "SA117505392", "merchandiser_id": anjali.id,
            "buyer_comments": "Approved for bulk. Keep the side vents at 4 cm; the buyer asked to watch the "
                              "collar roll on the XXL in bulk.",
        })
        self._xmlid(size_set, "sample_polo_size_set")
        size_set.action_start()
        if size_xl and (polo.current_techpack_id.measurement_ids):
            size_set.action_load_spec()
        offsets = [1.0, 0.0, 0.8, 0.8, -0.1, 0.0, 0.0, -0.3, 0.0, 0.2, 0.1, 0.3, -0.2]
        for m, off in zip(size_set.measurement_ids, offsets + [0.0] * 50):
            off = max(-m.tol_minus, min(m.tol_plus, off)) if (m.tol_plus or m.tol_minus) else 0.0
            m.measured = round(m.spec + off, 2) or 0.01
        size_set.sent_date = d(-65)
        size_set.action_send_to_buyer()
        size_set.decision_date = d(-57)
        size_set.action_approve()

    def _load_approvals(self, tee, polo, chino, jean, oxford, order_late):
        today = fields.Date.context_today(self)
        d = lambda n: today + timedelta(days=n)  # noqa: E731
        Approval = self.env["garment.approval"]
        anjali = self._ref(B + "user_anjali") or self.env.user
        fabric_jersey = self._ref(B + "product_fabric_jersey")
        fabric_poplin = self._ref(B + "product_fabric_poplin")
        cards = [
            ("approval_jean_wash", jean, "wash_standard", "colour_indigo", None, d(-6), "resubmit",
             [("A", "#2b3a55"), ("B", "#33476a")], None, 1),
            ("approval_tee_labdip_black", tee, "lab_dip", "colour_black", fabric_jersey, d(-9), "resubmit",
             [("A", "#1d1d1f"), ("B", "#27272b"), ("C", "#202024")], None, 1),
            ("approval_polo_strikeoff", polo, "strike_off", "colour_navy", None, d(-12), "resubmit",
             [("A", "#1f2a44")], None, 1),
            ("approval_jean_trim", jean, "trim_card", "colour_indigo", None, d(3), "with_buyer", [], None, 1),
            ("approval_oxford_labdip_white", oxford, "lab_dip", "colour_white", None, d(3), "with_buyer",
             [("A", "#fbfbf8"), ("B", "#f4f4ef")], None, 1),
            ("approval_oxford_labdip_sky", oxford, "lab_dip", "colour_sky", fabric_poplin, d(1), "with_buyer",
             [("A", "#8fbfe0"), ("B", "#99c4e3"), ("C", "#86b6da")], None, 2),
            ("approval_chino_labdip_grey", chino, "lab_dip", "colour_grey", None, d(-50), "approved",
             [("A", "#b9b7bd"), ("B", "#c2c0c6"), ("C", "#aeacb3")], "A", 1),
            ("approval_tee_trim_navy", tee, "trim_card", "colour_navy", None, d(-70), "approved", [], None, 1),
        ]
        for xmlid, style, kind, colour, material, due, state, options, chosen, submissions in cards:
            card = Approval.create({
                "style_id": style.id, "kind": kind, "colour_id": self._ref(B + colour).id,
                "material_id": material.id if material else False, "decision_due": due,
                "merchandiser_id": anjali.id, "courier": "SwiftAir Couriers",
                "order_id": order_late.id if style == tee else False,
                "option_ids": [Command.create({"name": n, "hex": h, "sequence": i}) for i, (n, h) in enumerate(options)],
            })
            self._xmlid(card, xmlid)
            for n in range(submissions):
                card.action_send()
                card.sent_date = due - timedelta(days=7)
                if n < submissions - 1:
                    card.buyer_comment = "Slightly too red; resubmit."
                    card.action_ask_resubmission()
            card.first_sent_date = due - timedelta(days=7 * submissions)
            if state == "resubmit":
                card.buyer_comment = "Too dark against the standard; please resubmit."
                card.action_ask_resubmission()
            elif state == "approved":
                if chosen:
                    card.chosen_option_id = card.option_ids.filtered(lambda o: o.name == chosen)
                card.buyer_comment = "Approved option %s. Watch the shade in bulk." % (chosen or "")
                card.decision_date = due + timedelta(days=2)
                card.action_approve()
