from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OPEN_ORDER_STATES = ("confirmed", "in_production", "packed")

COCKPITS = [
    ("pulse", "Factory Pulse"),
    ("orders", "Order Book"),
    ("costing", "Costing"),
    ("samples", "Samples"),
    ("tna", "Time & Action"),
    ("fabric", "Fabric Store"),
    ("cutting", "Cutting Room"),
    ("sewing", "Sewing Floor"),
    ("capacity", "Capacity"),
    ("jobwork", "Job Work"),
    ("quality", "Quality"),
    ("shipping", "Shipping"),
    ("wages", "Wages"),
    ("profit", "Profit"),
]


class GarmentCockpit(models.AbstractModel):
    """Read-only data layer of the cockpits. One method per cockpit; each returns
    {key, title, headline, tiles: [...], lists: [...], charts: [...]}. A tile carries the model and
    domain of its records so the client can open the filtered list."""

    _name = "garment.cockpit"
    _description = "Garment cockpit data"

    # ---------------------------------------------------------------- helpers
    def _tile(self, key, label, value, state="", model=None, domain=None, fmt="int"):
        return {"key": key, "label": label, "value": value, "state": state, "fmt": fmt,
                "model": model, "domain": domain or []}

    def _count(self, model, domain):
        return self.env[model].search_count(domain)

    def _sum(self, model, domain, fnames):
        """Totals of fields with one _read_group; non-stored fields are summed in Python (one search)."""
        Model = self.env[model]
        res = dict.fromkeys(fnames, 0)
        stored = [f for f in fnames if Model._fields[f].store]
        if stored:
            row = Model._read_group(domain, [], ["%s:sum" % f for f in stored])[0]
            res.update({f: v or 0 for f, v in zip(stored, row)})
        rest = [f for f in fnames if f not in stored]
        if rest:
            recs = Model.search(domain)
            for f in rest:
                res[f] = sum(recs.mapped(f))
        return res

    def _by(self, model, domain, groupby):
        """{group value: count} with one _read_group."""
        return {(g.id if hasattr(g, "id") else g): c
                for g, c in self.env[model]._read_group(domain, [groupby], ["__count"])}

    def _today(self):
        return fields.Date.context_today(self)

    def _company_domain(self):
        return [("company_id", "in", self.env.companies.ids)]

    # ------------------------------------------------------------- public API
    @api.model
    def get_cockpit_list(self):
        return [{"key": k, "title": t} for k, t in COCKPITS]

    @api.model
    def get_cockpit(self, key):
        if key not in dict(COCKPITS):
            raise UserError(_("There is no cockpit called %s.", key))
        data = getattr(self, "_cockpit_%s" % key)()
        data.update(key=key, title=dict(COCKPITS)[key], cockpits=self.get_cockpit_list(),
                    data_date=fields.Date.to_string(self._today()))
        return data

    # --------------------------------------------------------------- cockpits
    def _open_orders_domain(self):
        return self._company_domain() + [("state", "in", OPEN_ORDER_STATES)]

    def _late_orders_domain(self):
        return self._open_orders_domain() + [("ex_factory_date", "<", self._today())]

    def _cockpit_pulse(self):
        """Screen 5. Open orders, pieces, late orders, output today, DHU today, failed finals, cartons waiting."""
        today = self._today()
        Order = "garment.order"
        open_dom = self._open_orders_domain()
        late_dom = self._late_orders_domain()
        totals = self._sum(Order, open_dom, ["qty_ordered", "qty_cut", "qty_sewn", "qty_packed", "qty_shipped"])
        n_open = self._count(Order, open_dom)
        n_late = self._count(Order, late_dom)
        n_due7 = self._count(Order, open_dom + [("ex_factory_date", ">=", today),
                                                 ("ex_factory_date", "<=", today + timedelta(days=7))])
        sewing = self._cockpit_sewing()
        output_today = sum(r["output"] for r in sewing["lists"][0]["rows"])
        dhu_today = self._dhu(today)
        fail_dom = self._company_domain() + [("kind", "=", "final"), ("result", "=", "fail")]
        n_failed = self._count("garment.inspection", fail_dom)
        carton_dom = self._company_domain() + [("state", "=", "packed")]
        n_cartons = self._count("garment.carton", carton_dom)
        late = self.env[Order].search(late_dom, order="ex_factory_date", limit=10)
        tiles = [
            self._tile("orders_open", _("Orders open"), n_open, "", Order, open_dom),
            self._tile("pieces", _("Pieces on order"), totals["qty_ordered"], "", Order, open_dom),
            self._tile("late", _("Late orders"), n_late, "bad" if n_late else "good", Order, late_dom),
            self._tile("output_today", _("Output today"), output_today, "good", "garment.scan",
                       [("scanned_at", ">=", fields.Datetime.to_string(fields.Datetime.start_of(
                           fields.Datetime.now(), "day")))]),
            self._tile("dhu_today", _("DHU today"), dhu_today, "warn" if dhu_today else "good",
                       "garment.inspection", [("kind", "=", "inline")], fmt="pct"),
            self._tile("failed_finals", _("Failed finals"), n_failed, "bad" if n_failed else "good",
                       "garment.inspection", fail_dom),
            self._tile("cartons_waiting", _("Cartons waiting"), n_cartons, "warn", "garment.carton", carton_dom),
        ]
        return {
            "headline": {"open": n_open, "pieces": totals["qty_ordered"], "late": n_late, "due7": n_due7},
            "tiles": tiles,
            "charts": [
                {"key": "stage", "title": _("Pieces by stage, all open orders"), "type": "bar",
                 "labels": [_("Ordered"), _("Cut"), _("Sewn"), _("Packed"), _("Shipped")],
                 "values": [totals[f] for f in ("qty_ordered", "qty_cut", "qty_sewn", "qty_packed",
                                                "qty_shipped")]},
                {"key": "output", "title": _("Output by day, last 30 days"), "type": "line",
                 **self._output_by_day(30)},
            ],
            "lists": [
                {"key": "readings", "title": _("Department readings"),
                 "columns": [_("Department"), _("Reading"), _("Status")], "rows": self._readings(sewing)},
                {"key": "late", "title": _("Late orders"), "model": Order,
                 "columns": [_("Order"), _("Style"), _("Ex-factory"), _("Days late"), _("Packed")],
                 "rows": [{"id": o.id, "order": o.name, "style": o.style_id.display_name or "",
                           "ex_factory": fields.Date.to_string(o.ex_factory_date),
                           "days_late": (today - o.ex_factory_date).days,
                           "packed_pct": round(o.qty_packed * 100.0 / o.qty_ordered) if o.qty_ordered else 0}
                          for o in late]},
            ],
        }

    def _dhu(self, day):
        dom = self._company_domain() + [("kind", "=", "inline"),
                                         ("date", ">=", fields.Datetime.to_string(day)),
                                         ("date", "<", fields.Datetime.to_string(day + timedelta(days=1)))]
        t = self._sum("garment.inspection", dom, ["defect_count", "pieces_checked"])
        return round(t["defect_count"] * 100.0 / t["pieces_checked"], 1) if t["pieces_checked"] else 0.0

    def _output_by_day(self, days):
        """Pieces of the last operation per day (one _read_group on scans)."""
        today = self._today()
        start = today - timedelta(days=days - 1)
        Scan = self.env["garment.scan"]
        dom = [("scanned_at", ">=", fields.Datetime.to_string(start))]
        if "is_last_operation" in Scan._fields and Scan._fields["is_last_operation"].store:
            dom.append(("is_last_operation", "=", True))
        rows = dict(Scan._read_group(dom, ["scanned_at:day"], ["pieces:sum"]))
        labels, values = [], []
        for i in range(days):
            d = start + timedelta(days=i)
            labels.append(d.strftime("%d/%m"))
            values.append(sum(v for k, v in rows.items() if k and k.date() == d))
        return {"labels": labels, "values": values}

    def _readings(self, sewing):
        cs = self._count("garment.cost.sheet", self._company_domain() + [("state", "=", "submitted")]) \
            if "submitted" in dict(self.env["garment.cost.sheet"]._fields["state"].selection) else 0
        insp = self._count("garment.fabric.inspection", [("state", "!=", "done")]) \
            if "done" in dict(self.env["garment.fabric.inspection"]._fields["state"].selection) else 0
        fails = self._count("garment.inspection", self._company_domain() + [("kind", "=", "final"),
                                                                             ("result", "=", "fail")])
        behind = min(sewing["lists"][0]["rows"], key=lambda r: r["pct"], default=None)
        lays = self._sum("garment.lay", self._company_domain(), ["fabric_laid"])
        return [
            {"department": _("Merchandising"), "reading": _("%s cost sheets awaiting approval", cs),
             "status": "watch" if cs else "good"},
            {"department": _("Fabric store"), "reading": _("%s rolls to inspect", insp),
             "status": "watch" if insp else "good"},
            {"department": _("Cutting"), "reading": _("%s m fabric laid", round(lays["fabric_laid"])),
             "status": "good"},
            {"department": _("Sewing"), "reading": behind and _("%(line)s at %(pct)s%% of target",
                                                               line=behind["line"], pct=behind["pct"]) or "-",
             "status": behind and behind["pct"] < 85 and "behind" or "good"},
            {"department": _("Quality"), "reading": _("%s final failed", fails),
             "status": "blocked" if fails else "good"},
            {"department": _("Shipping"), "reading": _("%s cartons waiting",
                                                       self._count("garment.carton", [("state", "=", "packed")])),
             "status": "watch"},
        ]

    def _cockpit_sewing(self):
        """Screen 1. Output against target on every line; the line furthest behind."""
        lines = self.env["garment.line"].search(self._company_domain())
        rows = []
        for line in lines:  # few lines per factory; the sewing module computes each board
            board = line._garment_hourly_board()
            target = board["target"]
            rows.append({"id": line.id, "line": line.name, "output": board["output"], "target": target,
                         "pct": round(board["output"] * 100.0 / target) if target else 0,
                         "efficiency": board["efficiency"], "operators": line.operator_count,
                         "top_operator": board["top_operator"], "hours": board["hours"]})
        summaries = {line.id: line._garment_daily_summary() for line in lines}
        output = sum(r["output"] for r in rows)
        target = sum(r["target"] for r in rows)
        behind = min(rows, key=lambda r: r["pct"], default=None)
        eff = round(sum(r["efficiency"] for r in rows) / len(rows), 1) if rows else 0.0
        wip = sum(s["wip_pieces"] for s in summaries.values())
        lost = round(sum(s["lost_minutes"] for s in summaries.values()))
        Line = "garment.line"
        return {
            "headline": {"output": output, "target": target, "behind": behind and behind["line"] or "",
                         "behind_pct": behind and behind["pct"] or 0},
            "tiles": [
                self._tile("output", _("Output today"), output, "good", Line, []),
                self._tile("target", _("Target so far"), target, "", Line, []),
                self._tile("pct", _("Target achieved"), round(output * 100.0 / target, 1) if target else 0,
                           "good" if target and output >= target else "warn", Line, [], fmt="pct"),
                self._tile("efficiency", _("Efficiency today"), eff, "warn" if eff < 60 else "good",
                           Line, [], fmt="pct"),
                self._tile("operators", _("Operators sewing"), sum(lines.mapped("operator_count")), "", Line, []),
                self._tile("wip", _("Pieces on the lines"), wip, "", "garment.bundle",
                           [("line_id", "!=", False)]),
                self._tile("lost", _("Lost minutes today"), lost, "warn" if lost else "good", Line, []),
                self._tile("behind", _("Furthest behind"), behind and behind["line"] or "-",
                           "bad" if behind else "", Line,
                           behind and [("id", "=", behind["id"])] or [], fmt="text"),
            ],
            "charts": [{"key": "lines", "title": _("Output against target by line"), "type": "bar",
                        "labels": [r["line"] for r in rows], "values": [r["output"] for r in rows],
                        "targets": [r["target"] for r in rows]}],
            "lists": [{"key": "lines", "title": _("Lines"), "model": "garment.line",
                       "columns": [_("Line"), _("Output"), _("Target"), _("% of target"), _("Efficiency")],
                       "rows": rows}],
        }

    def _state_tiles(self, model, domain, labels, states=None):
        counts = self._by(model, domain, "state")
        tiles = []
        for st, label, tone in labels:
            tiles.append(self._tile(st, label, counts.get(st, 0), tone, model, domain + [("state", "=", st)]))
        return tiles, counts

    def _cockpit_orders(self):
        """Screen 6. Order book by state and buyer."""
        Order = "garment.order"
        dom = self._open_orders_domain()
        totals = self._sum(Order, dom, ["qty_ordered", "order_value"])
        late_dom = self._late_orders_domain()
        by_buyer = self.env[Order]._read_group(dom, ["buyer_id"], ["qty_ordered:sum", "__count"])
        return {
            "tiles": [
                self._tile("open", _("Orders open"), self._count(Order, dom), "", Order, dom),
                self._tile("pieces", _("Pieces"), totals["qty_ordered"], "", Order, dom),
                self._tile("value", _("Order value"), totals["order_value"], "good", Order, dom, fmt="money"),
                self._tile("late", _("Late"), self._count(Order, late_dom), "bad", Order, late_dom),
                self._tile("draft", _("Draft"), self._count(Order, self._company_domain() + [("state", "=", "draft")]),
                           "warn", Order, self._company_domain() + [("state", "=", "draft")]),
            ],
            "charts": [{"key": "buyer", "title": _("Pieces by buyer"), "type": "bar",
                        "labels": [b.display_name or _("None") for b, _q, _c in by_buyer],
                        "values": [q for _b, q, _c in by_buyer]}],
            "lists": [],
        }

    def _cockpit_costing(self):
        """Screen 7. Cost sheets by state, below the margin floor."""
        Cs = "garment.cost.sheet"
        dom = self._company_domain() + [("is_latest", "=", True)]
        counts = self._by(Cs, dom, "state")
        below = dom + [("below_floor", "=", True)] if self.env[Cs]._fields["below_floor"].store else None
        avg = self.env[Cs]._read_group(dom, [], ["margin_pct:avg"])[0][0] or 0.0
        tiles = [self._tile("sheets", _("Cost sheets"), sum(counts.values()), "", Cs, dom),
                 self._tile("margin", _("Average margin"), round(avg, 1), "good", Cs, dom, fmt="pct")]
        for st, n in sorted(counts.items()):
            tiles.append(self._tile(st, dict(self.env[Cs]._fields["state"]._description_selection(self.env)).get(st, st),
                                    n, "", Cs, dom + [("state", "=", st)]))
        if below is not None:
            tiles.append(self._tile("below", _("Below margin floor"), self._count(Cs, below), "bad", Cs, below))
        return {"tiles": tiles, "charts": [], "lists": []}

    def _cockpit_samples(self):
        """Screen 8. Samples and approvals waiting on the buyer."""
        S, A = "garment.sample", "garment.approval"
        sd, ad = self._company_domain(), self._company_domain()
        s = self._by(S, sd, "state")
        a = self._by(A, ad, "state")
        return {
            "tiles": [
                self._tile("s_open", _("Samples in work"), s.get("requested", 0) + s.get("in_progress", 0), "",
                           S, sd + [("state", "in", ("requested", "in_progress"))]),
                self._tile("s_buyer", _("Samples with buyer"), s.get("with_buyer", 0), "warn",
                           S, sd + [("state", "=", "with_buyer")]),
                self._tile("s_rejected", _("Samples rejected"), s.get("rejected", 0), "bad",
                           S, sd + [("state", "=", "rejected")]),
                self._tile("a_buyer", _("Approvals with buyer"), a.get("with_buyer", 0), "warn",
                           A, ad + [("state", "=", "with_buyer")]),
                self._tile("a_resubmit", _("To resubmit"), a.get("resubmit", 0), "bad",
                           A, ad + [("state", "=", "resubmit")]),
                self._tile("a_ok", _("Approved"), a.get("approved", 0), "good", A, ad + [("state", "=", "approved")]),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_tna(self):
        """Screen 9. Time-and-action milestones by status."""
        M = "garment.tna.milestone"
        dom = self._company_domain()
        c = self._by(M, dom, "status")
        labels = [("pending", _("Pending"), ""), ("on_time", _("On time"), "good"),
                  ("late", _("Done late"), "warn"), ("overdue", _("Overdue"), "bad")]
        return {"tiles": [self._tile(k, l, c.get(k, 0), t, M, dom + [("status", "=", k)]) for k, l, t in labels],
                "charts": [], "lists": []}

    def _cockpit_fabric(self):
        """Screen 10. Bookings in house / short, rolls inspected."""
        B, I = "garment.fabric.booking", "garment.fabric.inspection"
        bd = self._company_domain()
        b = self._by(B, bd, "state")
        r = self._by(I, [], "result") if self.env[I]._fields["result"].store else {}
        return {
            "tiles": [
                self._tile("bookings", _("Bookings open"), sum(v for k, v in b.items() if k != "in_house"), "",
                           B, bd + [("state", "!=", "in_house")]),
                self._tile("in_house", _("In house"), b.get("in_house", 0), "good",
                           B, bd + [("state", "=", "in_house")]),
                self._tile("ordered", _("Ordered"), b.get("ordered", 0), "warn", B, bd + [("state", "=", "ordered")]),
                self._tile("inspected", _("Rolls inspected"), self._count(I, []), "", I, []),
                self._tile("rejected", _("Rolls rejected"), r.get("reject", 0) or r.get("rejected", 0), "bad",
                           I, [("result", "in", ("reject", "rejected"))]),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_cutting(self):
        """Screen 11. Lays, pieces cut, bundles, fabric laid."""
        L, Bu = "garment.lay", "garment.bundle"
        dom = self._company_domain()
        t = self._sum(L, dom, ["pieces", "fabric_laid", "plies_actual"])
        avg = self.env[L]._read_group(dom, [], ["marker_efficiency:avg"])[0][0] or 0.0
        return {
            "tiles": [
                self._tile("lays", _("Lays"), self._count(L, dom), "", L, dom),
                self._tile("pieces", _("Pieces cut"), t["pieces"], "good", L, dom),
                self._tile("fabric", _("Fabric laid (m)"), round(t["fabric_laid"], 1), "", L, dom, fmt="float"),
                self._tile("marker", _("Marker efficiency"), round(avg, 1), "good" if avg >= 85 else "warn",
                           L, dom, fmt="pct"),
                self._tile("bundles", _("Bundles"), self._count(Bu, dom), "", Bu, dom),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_capacity(self):
        """Screen 12. Line plans: load against capacity, late and clashing bars."""
        P = "garment.line.plan"
        dom = self._company_domain()
        t = self._sum(P, dom, ["pieces", "minutes"])
        cap = self._sum("garment.line", self._company_domain(), ["capacity_minutes"])["capacity_minutes"]
        late = dom + [("is_late", "=", True)] if self.env[P]._fields["is_late"].store else dom + [("id", "=", 0)]
        return {
            "tiles": [
                self._tile("plans", _("Planned bars"), self._count(P, dom), "", P, dom),
                self._tile("pieces", _("Pieces planned"), t["pieces"], "", P, dom),
                self._tile("load", _("Load (min)"), round(t["minutes"]), "", P, dom),
                self._tile("capacity", _("Capacity per day (min)"), cap, "good", "garment.line", []),
                self._tile("late", _("Late bars"), self._count(P, late), "bad", P, late),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_jobwork(self):
        """Screen 13. Job work out, pending, overdue, value."""
        J = "garment.jobwork.order"
        dom = self._company_domain() + [("state", "!=", "cancel")]
        out = dom + [("state", "in", ("sent", "partly_received"))]
        t = self._sum(J, out, ["qty_sent", "qty_pending"])
        od = out + [("date_expected", "<", self._today())]
        return {
            "tiles": [
                self._tile("out", _("Orders out"), self._count(J, out), "", J, out),
                self._tile("sent", _("Pieces sent"), t["qty_sent"], "", J, out),
                self._tile("pending", _("Pieces pending"), t["qty_pending"], "warn", J, out),
                self._tile("overdue", _("Overdue"), self._count(J, od), "bad", J, od),
                self._tile("value", _("Job work value"), self._sum(J, dom, ["jobwork_value"])["jobwork_value"],
                           "", J, dom, fmt="money"),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_quality(self):
        """Screen 14. Inspections, DHU, failed finals, open CAPAs."""
        I, C = "garment.inspection", "garment.capa"
        dom = self._company_domain()
        fail = dom + [("result", "=", "fail")]
        t = self._sum(I, dom + [("kind", "=", "inline")], ["defect_count", "pieces_checked"])
        dhu = round(t["defect_count"] * 100.0 / t["pieces_checked"], 1) if t["pieces_checked"] else 0.0
        capa = dom + [("state", "in", ("open", "in_progress"))]
        return {
            "tiles": [
                self._tile("inspections", _("Inspections"), self._count(I, dom), "", I, dom),
                self._tile("dhu", _("DHU"), dhu, "warn" if dhu > 5 else "good", I, dom + [("kind", "=", "inline")],
                           fmt="pct"),
                self._tile("failed", _("Failed"), self._count(I, fail), "bad", I, fail),
                self._tile("failed_finals", _("Failed finals"), self._count(I, fail + [("kind", "=", "final")]),
                           "bad", I, fail + [("kind", "=", "final")]),
                self._tile("capa", _("Open CAPAs"), self._count(C, capa), "warn", C, capa),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_shipping(self):
        """Screen 15. Cartons by state, shipments."""
        Ca, Sh = "garment.carton", "garment.shipment"
        dom = self._company_domain()
        c = self._by(Ca, dom, "state")
        return {
            "tiles": [
                self._tile("planned", _("Cartons planned"), c.get("planned", 0), "", Ca, dom + [("state", "=", "planned")]),
                self._tile("packed", _("Cartons waiting"), c.get("packed", 0), "warn", Ca, dom + [("state", "=", "packed")]),
                self._tile("shipped", _("Cartons shipped"), c.get("shipped", 0), "good",
                           Ca, dom + [("state", "=", "shipped")]),
                self._tile("shipments", _("Shipments"), self._count(Sh, dom), "", Sh, dom),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_wages(self):
        """Screen 16. Wage sheets, net payable, top-up."""
        W = "garment.wage.sheet"
        dom = self._company_domain() + [("state", "!=", "cancel")]
        t = self._sum(W, dom, ["total_pieces", "total_net", "total_topup", "below_minimum_count"])
        todo = dom + [("state", "in", ("draft", "computed"))]
        return {
            "tiles": [
                self._tile("sheets", _("Sheets to approve"), self._count(W, todo), "warn", W, todo),
                self._tile("pieces", _("Pieces paid"), t["total_pieces"], "", W, dom),
                self._tile("net", _("Net payable"), t["total_net"], "", W, dom, fmt="money"),
                self._tile("topup", _("Minimum wage top-up"), t["total_topup"], "warn", W, dom, fmt="money"),
                self._tile("below", _("Operators below minimum"), t["below_minimum_count"], "bad", W, dom),
            ],
            "charts": [], "lists": [],
        }

    def _cockpit_profit(self):
        """Screen 17. Order profitability from the P&L module's summary."""
        P = "garment.order.pnl"
        s = self.env[P]._garment_profit_summary()
        closed = [("is_closed", "=", True)]
        return {
            "tiles": [
                self._tile("revenue", _("Revenue"), s["revenue"], "", P, closed, fmt="money"),
                self._tile("cost", _("Actual cost"), s["actual_cost"], "", P, closed, fmt="money"),
                self._tile("margin", _("Margin"), s["margin_pct"], "good" if s["margin_pct"] > 0 else "bad",
                           P, closed, fmt="pct"),
                self._tile("vs_plan", _("Cost vs plan"), s["cost_vs_plan_pct"], "warn", P, closed, fmt="pct"),
                self._tile("loss", _("Loss orders"), s["loss_count"], "bad", P, closed + [("is_loss", "=", True)]),
            ],
            "charts": [{"key": "buyer", "title": _("Margin by buyer"), "type": "bar",
                        "labels": [b["buyer"] for b in s["margin_by_buyer"]],
                        "values": [b["margin_pct"] for b in s["margin_by_buyer"]]}],
            "lists": [],
        }
