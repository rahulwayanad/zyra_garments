import re
from collections import defaultdict
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

OPEN_ORDER_STATES = ("confirmed", "in_production", "packed")
WORKING_DAYS_PER_WEEK = 6  # Monday to Saturday, the usual garment-factory week

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

# chart colours (the theme's violet, green, amber, red; light violet for targets and capacity)
VIOLET, GREEN, AMBER, RED = "#6d4ee8", "#12a37f", "#d98a04", "#e5484d"
LIGHT, MID, GREY, BLUE, PINK = "#cfc6f5", "#8f7fd9", "#94a3b8", "#3b82f6", "#d6409f"
SERIES = [VIOLET, GREEN, AMBER, BLUE, PINK, MID]


class GarmentCockpit(models.AbstractModel):
    """Read-only data layer of the cockpits. One method per cockpit; each returns
    {subtitle, headline: [parts], tiles: [...], panels: [...]}. A tile carries the model and domain of its
    records so the client can open the filtered list. Panels are drawn in order, two per row:
    chart (bar/line), donut, hbars (ranked horizontal bars) or table."""

    _name = "garment.cockpit"
    _description = "Garment cockpit data"

    # ---------------------------------------------------------------- helpers
    def _tile(self, key, label, value, state="", model=None, domain=None, fmt="int", display=None, note=None):
        return {"key": key, "label": label, "value": value, "state": state, "fmt": fmt,
                "display": display, "note": note, "model": model, "domain": domain or []}

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
        """{group value: count} with one _read_group (non-stored field: one search, counted in Python)."""
        Model = self.env[model]
        if not Model._fields[groupby].store:
            res = {}
            for rec in Model.search(domain):
                res[rec[groupby]] = res.get(rec[groupby], 0) + 1
            return res
        return {(g.id if hasattr(g, "id") else g): c
                for g, c in self.env[model]._read_group(domain, [groupby], ["__count"])}

    def _today(self):
        return fields.Date.context_today(self)

    def _days(self):
        return self.env.context.get("cockpit_days") or 30

    def _period_start(self):
        return self._today() - timedelta(days=self._days() - 1)

    def _company_domain(self):
        return [("company_id", "in", self.env.companies.ids)]

    def _scope(self, model, domain=None):
        """Company + the buyer and business-model filters, on any model that can carry them."""
        M = self.env[model]
        dom = list(domain or [])
        if "company_id" in M._fields:
            dom = ["|", ("company_id", "=", False), ("company_id", "in", self.env.companies.ids)] + dom
        buyer = self.env.context.get("cockpit_buyer_id")
        bm = self.env.context.get("cockpit_business_model")
        if not (buyer or bm):
            return dom
        if model == "garment.order":
            order_path = ""
        else:
            order_path = next((f + "." for f in ("order_id", "production_order_id", "garment_order_id")
                               if f in M._fields and M._fields[f].comodel_name == "garment.order"), None)
        if buyer:
            if "buyer_id" in M._fields:
                dom.append(("buyer_id", "=", int(buyer)))
            elif order_path is not None:
                dom.append((order_path + "buyer_id", "=", int(buyer)))
        if bm and order_path is not None:
            dom.append((order_path + "business_model", "=", bm))
        return dom

    def _money(self, value, short=True, currency=None):
        """Money as the screens show it: ₹4.82 L / ₹9,140 for rupees, $242.4k / $9,140 otherwise."""
        cur = currency or self.env.company.currency_id
        sym = cur.symbol or ""
        sign = "−" if value < 0 else ""
        v = abs(value or 0.0)
        if cur.name == "INR":
            if short and v >= 100000:
                text = "%.2f L" % (v / 100000)
            else:
                n = str(int(round(v)))
                if len(n) > 3:
                    n = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", n[:-3]) + "," + n[-3:]
                text = n
        elif short and v >= 10000:
            text = ("%.1f" % (v / 1000)).rstrip("0").rstrip(".") + "k"
        else:
            text = "{:,}".format(int(round(v)))
        return sign + (text + " " + sym if cur.position == "after" else sym + text)

    def _money_unit(self):
        """(divisor, label) for money on chart axes: lakh for rupees, thousands otherwise."""
        return (100000, "L") if self.env.company.currency_id.name == "INR" else (1000, "k")

    @staticmethod
    def _n(n, one, many):
        """'1 order' / '3 orders' — the count with the right noun."""
        return "%s %s" % (n, one if n == 1 else many)

    @staticmethod
    def _d(d):
        return d and "%d %s" % (d.day, d.strftime("%b")) or ""

    @staticmethod
    def _pct(part, whole, digits=1):
        return round(part * 100.0 / whole, digits) if whole else 0.0

    def _buckets(self):
        """Time buckets for the period: days up to a month, weeks up to ~4 months, months beyond."""
        days, start, today = self._days(), self._period_start(), self._today()
        if days <= 31:
            return [(start + timedelta(days=i)).strftime("%d") for i in range(days)], \
                [(start + timedelta(days=i), start + timedelta(days=i)) for i in range(days)]
        if days <= 120:
            first = start - timedelta(days=start.weekday())
            res, d = [], first
            while d <= today:
                res.append((d, d + timedelta(days=6)))
                d += timedelta(days=7)
            return ["Wk %s" % b[0].isocalendar()[1] for b in res], res
        return self._months(start, today)

    @staticmethod
    def _months(start, end):
        res, d = [], date(start.year, start.month, 1)
        while d <= end:
            nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
            res.append((d, nxt - timedelta(days=1)))
            d = nxt
        return [b[0].strftime("%b") for b in res], res

    @staticmethod
    def _bucket_of(buckets, day):
        if hasattr(day, "hour"):
            day = day.date()
        for i, (a, b) in enumerate(buckets):
            if a <= day <= b:
                return i
        return None

    # panels
    def _chart(self, key, title, kind, labels, series, stacked=False, value_labels=False, ref=None,
               legend=True, unit=""):
        return {"type": "chart", "key": key, "title": title, "kind": kind, "labels": labels, "series": series,
                "stacked": stacked, "value_labels": value_labels, "ref": ref, "legend": legend, "unit": unit}

    def _donut(self, key, title, segments, model=None):
        return {"type": "donut", "key": key, "title": title, "model": model,
                "segments": segments, "total": sum(s["value"] for s in segments)}

    def _hbars(self, key, title, rows, scale=None):
        top = scale or max([r["value"] for r in rows] + [0]) * 1.15 or 1
        for r in rows:
            r["width"] = max(0, min(100, round(r["value"] * 100.0 / top, 1)))
        return {"type": "hbars", "key": key, "title": title, "rows": rows}

    def _tbl(self, key, title, columns, rows, model=None):
        """columns: [(label, align)]; rows: {id, tone, cells: [text | {pct, tone} | {badge, tone}]}."""
        return {"type": "table", "key": key, "title": title, "model": model,
                "columns": [{"label": c, "align": a} for c, a in columns], "rows": rows}

    # ------------------------------------------------------------- public API
    @api.model
    def get_cockpit_list(self):
        return [{"key": k, "title": t} for k, t in COCKPITS]

    @api.model
    def get_cockpit(self, key, filters=None):
        if key not in dict(COCKPITS):
            raise UserError(_("There is no cockpit called %s.", key))
        filters = dict(filters or {})
        days = int(filters.get("days") or 30)
        self = self.with_context(cockpit_days=days, cockpit_buyer_id=filters.get("buyer_id") or False,
                                 cockpit_business_model=filters.get("business_model") or False)
        data = getattr(self, "_cockpit_%s" % key)()
        today = self._today()
        Order = self.env["garment.order"]
        data["filters"] = {
            "days": days, "buyer_id": filters.get("buyer_id") or False,
            "business_model": filters.get("business_model") or False,
            "date_from": fields.Date.to_string(today - timedelta(days=days - 1)),
            "date_to": fields.Date.to_string(today),
            "buyers": [{"id": p.id, "name": p.display_name}
                       for p in Order.search(self._company_domain()).buyer_id],
            "business_models": [{"key": k, "name": v} for k, v in
                                Order._fields["business_model"]._description_selection(self.env)],
        }
        data.update(key=key, title=dict(COCKPITS)[key], cockpits=self.get_cockpit_list(),
                    data_date=self._d(today) + " " + str(today.year))
        return data

    # ------------------------------------------------------------ shared reads
    def _open_orders_domain(self):
        return self._scope("garment.order", [("state", "in", OPEN_ORDER_STATES)])

    def _late_orders_domain(self):
        return self._open_orders_domain() + [("ex_factory_date", "<", self._today())]

    def _dhu(self, day):
        dom = self._scope("garment.inspection", [
            ("kind", "=", "inline"), ("date", ">=", fields.Datetime.to_string(day)),
            ("date", "<", fields.Datetime.to_string(day + timedelta(days=1)))])
        t = self._sum("garment.inspection", dom, ["defect_count", "pieces_checked"])
        return self._pct(t["defect_count"], t["pieces_checked"])

    def _dhu_limit(self):
        return self.env.company.garment_dhu_limit or 5.0

    def _output_by_day(self, days):
        """Pieces of the last operation per day (one _read_group on scans)."""
        today = self._today()
        start = today - timedelta(days=days - 1)
        Scan = self.env["garment.scan"]
        dom = [("scanned_at", ">=", fields.Datetime.to_string(start))]
        if "is_last_operation" in Scan._fields and Scan._fields["is_last_operation"].store:
            dom.append(("is_last_operation", "=", True))
        rows = Scan._read_group(dom, ["scanned_at:day"], ["pieces:sum"])
        per_day = defaultdict(int)
        for k, v in rows:
            if k:
                per_day[k.date() if hasattr(k, "hour") else k] += v
        labels = [(start + timedelta(days=i)).strftime("%d/%m") for i in range(days)]
        return labels, [per_day.get(start + timedelta(days=i), 0) for i in range(days)]

    def _fabric_utilisation(self):
        """Share of the fabric laid that ends up in cut pieces: marker efficiency × marker length × plies,
        over fabric laid (so end loss and splicing count against it), for lays that were cut."""
        lays = self.env["garment.lay"].search(self._scope("garment.lay", [("state", "in", ("cut", "bundled"))]))
        used = sum(l.marker_efficiency / 100.0 * l.lay_length * l.plies_actual for l in lays)
        return self._pct(used, sum(lays.mapped("fabric_laid")))

    def _expiring_lcs(self, within):
        today = self._today()
        return self.env["garment.lc"].search(self._scope("garment.lc", [
            ("state", "=", "open"), ("expiry_date", ">=", today),
            ("expiry_date", "<=", today + timedelta(days=within))]), order="expiry_date")

    # --------------------------------------------------------------- cockpits
    def _cockpit_pulse(self):
        """Screen 5. Orders, the floor and shipments on one screen."""
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
        output_today = sewing["headline_data"]["output"]
        dhu_today = self._dhu(today)
        fail_dom = self._scope("garment.inspection", [("kind", "=", "final"), ("result", "=", "failed")])
        n_failed = self._count("garment.inspection", fail_dom)
        carton_dom = self._scope("garment.carton", [("state", "=", "packed")])
        n_cartons = self._count("garment.carton", carton_dom)
        late = self.env[Order].search(late_dom, order="ex_factory_date", limit=10)
        limit = self._dhu_limit()
        labels, values = self._output_by_day(self._days())
        stage = [totals[f] for f in ("qty_ordered", "qty_cut", "qty_sewn", "qty_packed", "qty_shipped")]
        return {
            "subtitle": _("Orders, the floor and shipments on one screen"),
            "headline": [{"t": "%s" % n_open, "tone": "b"}, _(" orders open for "),
                         {"t": "{:,}".format(totals["qty_ordered"]), "tone": "b"}, _(" pieces. "),
                         {"t": _("%s past their ex-factory date", n_late), "tone": "bad" if n_late else "b"},
                         _(", %s due within 7 days.", n_due7)],
            "headline_data": {"open": n_open, "pieces": totals["qty_ordered"], "late": n_late, "due7": n_due7},
            "tiles": [
                self._tile("orders_open", _("Orders open"), n_open, "", Order, open_dom),
                self._tile("pieces", _("Pieces on order"), totals["qty_ordered"], "", Order, open_dom),
                self._tile("late", _("Late orders"), n_late, "bad" if n_late else "good", Order, late_dom),
                self._tile("output_today", _("Output today"), output_today, "good", "garment.scan",
                           [("scanned_at", ">=", fields.Datetime.to_string(fields.Datetime.start_of(
                               fields.Datetime.now(), "day")))]),
                self._tile("dhu_today", _("DHU today"), dhu_today,
                           "bad" if dhu_today > limit else "warn" if dhu_today >= 0.8 * limit else "good",
                           "garment.inspection", [("kind", "=", "inline")], fmt="pct"),
                self._tile("failed_finals", _("Failed finals"), n_failed, "bad" if n_failed else "good",
                           "garment.inspection", fail_dom),
                self._tile("cartons_waiting", _("Cartons waiting"), n_cartons, "warn" if n_cartons else "",
                           "garment.carton", carton_dom),
            ],
            "panels": [
                self._tbl("readings", _("Department readings"),
                            [(_("Department"), "start"), (_("Reading"), "start"), (_("Status"), "start")],
                            self._readings(sewing)),
                self._chart("output", _("Output by day, last %s days", self._days()), "line", labels,
                            [{"label": _("Pieces sewn"), "values": values, "color": VIOLET}]),
                self._chart("stage", _("Pieces by stage, all open orders"), "bar",
                            [_("Ordered"), _("Cut"), _("Sewn"), _("Packed"), _("Shipped")],
                            [{"label": _("Pieces"), "values": stage, "color": VIOLET}],
                            value_labels=True, legend=False),
                self._tbl("late", _("Late orders"),
                            [(_("Order"), "start"), (_("Style"), "start"), (_("Ex-factory"), "start"),
                             (_("Days late"), "end"), (_("Packed"), "start")],
                            [{"id": o.id, "tone": "bad",
                              "cells": [o.name, o.style_id.display_name or "", self._d(o.ex_factory_date),
                                        (today - o.ex_factory_date).days,
                                        {"pct": round(self._pct(o.qty_packed, o.qty_ordered, 0)), "tone": "violet"}]}
                             for o in late], model=Order),
            ],
        }

    def _readings(self, sewing):
        cs = self._count("garment.cost.sheet", self._scope("garment.cost.sheet", [("state", "=", "submitted")]))
        to_inspect = self._count("stock.lot", self._scope("stock.lot", [("roll_status", "=", "received")]))
        fails = self._count("garment.inspection", self._scope("garment.inspection", [
            ("kind", "=", "final"), ("result", "=", "failed")]))
        rows = sewing["line_rows"]
        behind = min(rows, key=lambda r: r["pct"], default=None)
        util = self._fabric_utilisation()
        lc = self._expiring_lcs(30)[:1]
        cartons = self._count("garment.carton", self._scope("garment.carton", [("state", "=", "packed")]))
        badge = {"good": (_("Good"), "good"), "watch": (_("Watch"), "warn"),
                 "behind": (_("Behind"), "bad"), "blocked": (_("Blocked"), "bad")}
        readings = [
            (_("Merchandising"), _("%s cost sheets awaiting approval", cs), "watch" if cs else "good"),
            (_("Fabric store"), _("%s rolls to inspect", to_inspect), "watch" if to_inspect else "good"),
            (_("Cutting"), _("%s%% fabric utilisation", util), "good" if util >= 85 else "watch"),
            (_("Sewing"), behind and _("%(line)s at %(pct)s%% of target", line=behind["line"], pct=behind["pct"])
             or "-", behind and behind["pct"] < 85 and "behind" or "good"),
            (_("Quality"), _("%s final failed", fails), "blocked" if fails else "good"),
            (_("Shipping"), lc and _("LC %(lc)s expires in %(days)s days", lc=lc.name,
                                     days=(lc.expiry_date - self._today()).days)
             or _("%s cartons waiting", cartons), "watch" if lc or cartons else "good"),
        ]
        return [{"cells": [dep, reading, {"badge": badge[st][0], "tone": badge[st][1]}]}
                for dep, reading, st in readings]

    def _cockpit_sewing(self):
        """Screen 1. Target against output on every line, hour by hour, and what is holding it back."""
        lines = self.env["garment.line"].search(self._company_domain())
        rows = []
        for line in lines:  # few lines per factory; the sewing module computes each board
            board = line._garment_hourly_board()
            target = board["target"]
            rows.append({"id": line.id, "line": line.name, "output": board["output"], "target": target,
                         "pct": round(board["output"] * 100.0 / target) if target else 0,
                         "efficiency": board["efficiency"], "hours": board["hours"]})
        summaries = {line.id: line._garment_daily_summary() for line in lines}
        output = sum(r["output"] for r in rows)
        target = sum(r["target"] for r in rows)
        behind = min(rows, key=lambda r: r["pct"], default=None)
        eff = round(sum(r["efficiency"] for r in rows) / len(rows), 1) if rows else 0.0
        eff_target = round(sum(lines.mapped("target_efficiency")) / len(lines), 1) if lines else 0.0
        wip = sum(s["wip_pieces"] for s in summaries.values())
        lost = round(sum(s["lost_minutes"] for s in summaries.values()))
        Line = "garment.line"
        today = self._today()
        down = self.env["garment.line.day.downtime"].search(
            [("day_id.date", "=", today), ("day_id.line_id", "in", lines.ids)], order="create_date")
        open_down = down.filtered(lambda d: d.day_id.state == "open")
        machines_down = down.filtered("machine_type_id")
        start = self._period_start()
        eff_rows = {}
        for d, e, p in self.env["garment.line.day"]._read_group(
                [("date", ">=", start), ("line_id", "in", lines.ids)], ["date:day"],
                ["efficiency:avg", "planned_efficiency:avg"]):
            if d:
                eff_rows[d.date() if hasattr(d, "hour") else d] = (e, p)
        eff_labels, eff_vals, std_vals = [], [], []
        for i in range(self._days()):
            d = start + timedelta(days=i)
            e, p = eff_rows.get(d, (None, None))
            eff_labels.append(d.strftime("%d/%m"))
            eff_vals.append(round(e, 1) if e is not None else None)
            std_vals.append(round(p, 1) if p is not None else None)
        hour_labels, hour_out, hour_tgt = [], {}, {}
        for r in rows:
            for h in r["hours"]:
                if h["hour"] not in hour_out:
                    hour_labels.append(h["hour"])
                hour_out[h["hour"]] = hour_out.get(h["hour"], 0) + h["output"]
                hour_tgt[h["hour"]] = hour_tgt.get(h["hour"], 0) + h["target"]
        headline = [{"t": "{:,}".format(output), "tone": "b"}, _(" pieces off the lines against a target of "),
                    {"t": "{:,}".format(target), "tone": "b"}, _(" so far.")]
        if behind:
            headline += [" ", {"t": behind["line"], "tone": "bad"}, _(" is furthest behind at "),
                         {"t": "%s%%" % behind["pct"], "tone": "bad"}, _(" of its target.")]
        return {
            "subtitle": _("Target against output on every line, hour by hour, and what is holding it back"),
            "headline": headline,
            "headline_data": {"output": output, "target": target, "behind": behind and behind["line"] or "",
                              "behind_pct": behind and behind["pct"] or 0},
            "line_rows": rows,
            "tiles": [
                self._tile("output", _("Output today"), output, "good", Line, []),
                self._tile("target", _("Target so far"), target, "", Line, []),
                self._tile("pct", _("Target achieved"), self._pct(output, target),
                           "good" if target and output >= target else "warn", Line, [], fmt="pct"),
                self._tile("efficiency", _("Efficiency today"), eff, "good" if eff >= eff_target else "warn",
                           Line, [], fmt="pct", note=_("target %s%%", round(eff_target))),
                self._tile("operators", _("Operators sewing"), sum(lines.mapped("operator_count")), "", Line, []),
                self._tile("wip", _("Pieces on the lines"), wip, "", "garment.bundle", [("line_id", "!=", False)],
                           note=_("issued, not yet sewn")),
                self._tile("lost", _("Lost minutes today"), lost, "warn" if lost else "good",
                           "garment.line.day.downtime", [("id", "in", down.ids)]),
                self._tile("stopped", _("Lines stopped now"), len(open_down.day_id.line_id),
                           "bad" if open_down else "good", "garment.line.day.downtime", [("id", "in", open_down.ids)]),
                self._tile("machines_down", _("Machines down"), len(machines_down),
                           "bad" if machines_down else "good", "garment.line.day.downtime",
                           [("id", "in", machines_down.ids)]),
            ],
            "panels": [
                self._chart("lines", _("Target against output today, by line"), "bar", [r["line"] for r in rows],
                            [{"label": _("Target so far"), "values": [r["target"] for r in rows], "color": MID},
                             {"label": _("Output"), "values": [r["output"] for r in rows], "color": GREEN}],
                            value_labels=True),
                self._chart("efficiency", _("Efficiency, last %s days", self._days()), "line", eff_labels,
                            [{"label": _("Efficiency %"), "values": eff_vals, "color": VIOLET},
                             {"label": _("On-standard %"), "values": std_vals, "color": AMBER}],
                            ref=eff_target),
                self._chart("hours", _("Pieces per hour by line, %s", self._d(today)), "bar", hour_labels,
                            [{"label": _("Target"), "values": [hour_tgt[h] for h in hour_labels], "color": LIGHT},
                             {"label": _("Output"), "values": [hour_out[h] for h in hour_labels], "color": VIOLET}]),
                self._tbl("stopped", _("Lines that stopped today"),
                            [(_("Line"), "start"), (_("Reason"), "start"), (_("Since"), "start"),
                             (_("Minutes lost"), "end")],
                            [{"id": d.id, "cells": [d.day_id.line_id.name, d.reason,
                                                    fields.Datetime.context_timestamp(self, d.create_date)
                                                    .strftime("%H:%M"), d.minutes]} for d in down],
                            model="garment.line.day.downtime"),
            ],
        }

    def _cockpit_orders(self):
        """Screen 6. What the factory has promised and how far each order has gone."""
        Order = "garment.order"
        today = self._today()
        dom = self._open_orders_domain()
        late_dom = self._late_orders_domain()
        due_dom = dom + [("ex_factory_date", ">=", today), ("ex_factory_date", "<=", today + timedelta(days=7))]
        totals = self._sum(Order, dom, ["qty_ordered", "qty_packed", "order_value"])
        orders = self.env[Order].search(dom, order="ex_factory_date")
        late = self.env[Order].search(late_dom)
        n_late = len(late)
        # an order packed beyond its quantity has nothing left to pack (it does not offset another order)
        to_pack_late = sum(max(o.qty_ordered - o.qty_packed, 0) for o in late)
        to_pack = sum(max(o.qty_ordered - o.qty_packed, 0) for o in orders)
        # orders by ex-factory month and business model
        months = sorted({date(o.ex_factory_date.year, o.ex_factory_date.month, 1) for o in orders if o.ex_factory_date})
        models_sel = self.env[Order]._fields["business_model"]._description_selection(self.env)
        series = []
        for i, (bm, _label) in enumerate(models_sel):
            counts = [len(orders.filtered(lambda o, m=m, bm=bm: o.business_model == bm and o.ex_factory_date
                                          and o.ex_factory_date.replace(day=1) == m)) for m in months]
            series.append({"label": bm.upper(), "values": counts, "color": SERIES[i % len(SERIES)]})

        def bar(qty, o, good_at=90.0, tone="violet"):
            pct = round(self._pct(qty, o.qty_ordered, 0))
            return {"pct": pct, "tone": tone if tone == "violet" else ("good" if pct >= good_at else "warn")}

        return {
            "subtitle": _("What the factory has promised and how far each order has gone"),
            "headline": [{"t": self._n(n_late, _("order"), _("orders")), "tone": "bad" if n_late else "b"},
                         _(" is past its ex-factory date with ") if n_late == 1 else _(" are past their ex-factory date with "),
                         {"t": "{:,}".format(to_pack_late), "tone": "b"}, _(" pieces still to pack.")],
            "tiles": [
                self._tile("open", _("Open orders"), len(orders), "", Order, dom),
                self._tile("to_pack", _("Pieces to pack"), to_pack, "", Order, dom),
                self._tile("late", _("Past ex-factory"), n_late, "bad" if n_late else "good", Order, late_dom),
                self._tile("due7", _("Due in 7 days"), self._count(Order, due_dom), "warn", Order, due_dom),
                self._tile("value", _("Order value"), totals["order_value"], "", Order, dom, fmt="money",
                           display=self._money(totals["order_value"])),
            ],
            "panels": [
                self._chart("months", _("Orders by ex-factory month and business model"), "bar",
                            [m.strftime("%b") for m in months], series, stacked=True),
                self._tbl("stages", _("Stage completion by order"),
                            [(_("Order"), "start"), (_("Style"), "start"), (_("Cut"), "start"),
                             (_("Sewn"), "start"), (_("Packed"), "start")],
                            [{"id": o.id, "cells": [o.name, o.style_id.display_name or "",
                                                    bar(o.qty_cut, o), bar(o.qty_sewn, o, tone="auto"),
                                                    bar(o.qty_packed, o, tone="auto")]} for o in orders[:10]],
                            model=Order),
            ],
        }

    def _cockpit_costing(self):
        """Screen 7. Approved prices, margins and the sheets waiting on a decision."""
        Cs = "garment.cost.sheet"
        today = self._today()
        year_ago = today - timedelta(days=365)
        approved = self._scope(Cs, [("state", "=", "approved"), ("approved_date", ">=", year_ago)])
        waiting = self._scope(Cs, [("state", "=", "submitted")])
        under = approved + [("below_floor", "=", True)]
        sheets = self.env[Cs].search(approved)
        avg = round(sum(sheets.mapped("margin_pct")) / len(sheets), 1) if sheets else 0.0
        floor = self.env.company.margin_floor_pct
        n_under = self._count(Cs, under)
        quoted = sum(sheets.mapped("quoted_value"))
        labels, buckets = self._months(date(today.year - 1, today.month, 1) + timedelta(days=32), today)
        per = defaultdict(list)
        for s in sheets:
            i = self._bucket_of(buckets, s.approved_date)
            if i is not None:
                per[i].append(s.margin_pct)
        values = [round(sum(per[i]) / len(per[i]), 1) if per[i] else None for i in range(len(buckets))]
        return {
            "subtitle": _("Approved prices, margins and the sheets waiting on a decision"),
            "headline": [_("Average approved margin is "), {"t": "%s%%" % avg, "tone": "b"}, _(" over 12 months; "),
                         {"t": self._n(n_under, _("sheet"), _("sheets")), "tone": "bad" if n_under else "b"},
                         (_(" was approved under the %s%% floor.", round(floor, 1)) if n_under == 1
                          else _(" were approved under the %s%% floor.", round(floor, 1)))],
            "tiles": [
                self._tile("approved", _("Sheets approved"), len(sheets), "", Cs, approved),
                self._tile("margin", _("Average margin"), avg, "good" if avg >= floor else "bad", Cs, approved,
                           fmt="pct"),
                self._tile("waiting", _("Awaiting approval"), self._count(Cs, waiting), "warn", Cs, waiting),
                self._tile("under", _("Under floor"), n_under, "bad" if n_under else "good", Cs, under),
                self._tile("quoted", _("Quoted value"), quoted, "", Cs, approved, fmt="money",
                           display=self._money(quoted)),
            ],
            "panels": [
                self._chart("margin", _("Average margin by month"), "line", labels,
                            [{"label": _("Margin %"), "values": values, "color": VIOLET}], ref=floor),
                self._tbl("under", _("Sheets under the margin floor"),
                            [(_("Sheet"), "start"), (_("Style"), "start"), (_("Buyer"), "start"),
                             (_("Margin"), "end"), (_("Reason"), "start")],
                            [{"id": s.id, "tone": "bad",
                              "cells": [s.name, s.style_id.display_name or s.style_label or "",
                                        s.buyer_id.display_name or "", "%.1f%%" % s.margin_pct,
                                        s.floor_override_reason or ""]}
                             for s in self.env[Cs].search(under, order="approved_date desc", limit=10)],
                            model=Cs),
            ],
        }

    def _cockpit_samples(self):
        """Screen 8. Samples and buyer approvals that hold an order back."""
        S, A, Order = "garment.sample", "garment.approval", "garment.order"
        sd = self._scope(S)
        open_dom = sd + [("state", "not in", ("approved", "rejected"))]
        samples = self.env[S].search(open_dom)
        late_ids = samples.filtered("is_overdue").ids
        cards = self.env[A].search(self._scope(A, [("state", "in", ("draft", "resubmit", "with_buyer"))]))
        overdue_cards = cards.filtered("is_overdue").ids
        buyer_dom = sd + [("state", "=", "with_buyer")]
        orders = self.env[Order].search(self._open_orders_domain())
        no_pp = orders.filtered(lambda o: not o.pp_sample_ok).ids
        types = [t for t in self.env[S]._fields["sample_type"]._description_selection(self.env) if t[0] != "salesman"]
        room = [len(samples.filtered(lambda s, t=t: s.sample_type == t and s.state in ("requested", "in_progress")))
                for t, _l in types]
        with_buyer = [len(samples.filtered(lambda s, t=t: s.sample_type == t and s.state == "with_buyer"))
                      for t, _l in types]
        today = self._today()
        waiting = self.env[A].search(self._scope(A, [("state", "=", "with_buyer")]), order="sent_date", limit=10)
        return {
            "subtitle": _("Samples and buyer approvals that hold an order back"),
            "headline": [{"t": self._n(len(late_ids), _("sample"), _("samples")), "tone": "bad" if late_ids else "b"},
                         _(" is late and ") if len(late_ids) == 1 else _(" are late and "),
                         {"t": self._n(len(no_pp), _("order"), _("orders")), "tone": "b"},
                         _(" has no approved pre-production sample.") if len(no_pp) == 1
                         else _(" have no approved pre-production sample.")],
            "tiles": [
                self._tile("s_open", _("Samples open"), len(samples), "", S, open_dom),
                self._tile("s_late", _("Late samples"), len(late_ids), "bad" if late_ids else "good",
                           S, [("id", "in", late_ids)]),
                self._tile("a_overdue", _("Approval cards overdue"), len(overdue_cards),
                           "warn" if overdue_cards else "good", A, [("id", "in", overdue_cards)]),
                self._tile("s_buyer", _("With the buyer"), self._count(S, buyer_dom), "", S, buyer_dom),
                self._tile("no_pp", _("Orders without PP sample"), len(no_pp), "bad" if no_pp else "good",
                           Order, [("id", "in", no_pp)]),
            ],
            "panels": [
                self._chart("types", _("Samples by type and stage"), "bar", [l for _t, l in types],
                            [{"label": _("In the sample room"), "values": room, "color": VIOLET},
                             {"label": _("With the buyer"), "values": with_buyer, "color": GREEN}], stacked=True),
                self._tbl("waiting", _("Waiting on the buyer"),
                            [(_("Card"), "start"), (_("Kind"), "start"), (_("Style"), "start"),
                             (_("Sent"), "start"), (_("Waiting"), "end")],
                            [{"id": a.id, "cells": [
                                a.name, dict(self.env[A]._fields["kind"]._description_selection(self.env)).get(a.kind, ""),
                                a.style_id.display_name or "", self._d(a.sent_date),
                                a.sent_date and _("%s d", (today - a.sent_date).days) or ""]} for a in waiting],
                            model=A),
            ],
        }

    def _cockpit_tna(self):
        """Screen 9. Every order's milestones against plan."""
        M = "garment.tna.milestone"
        today = self._today()
        dom = self._scope(M)
        milestones = self.env[M].search(dom)
        open_ms = milestones.filtered(lambda m: not m.actual_date)
        overdue = open_ms.filtered(lambda m: m.status == "overdue")
        due_week = open_ms.filtered(lambda m: m.planned_date and today <= m.planned_date <= today + timedelta(days=7))

        def on_time_share(a, b):
            done = milestones.filtered(lambda m: m.actual_date and a <= m.actual_date <= b)
            return round(self._pct(len(done.filtered(lambda m: m.status == "on_time")), len(done), 0)) \
                if done else None

        month_start = today.replace(day=1)
        this_month = on_time_share(month_start, today) or 0
        labels, buckets = self._months((month_start - timedelta(days=150)).replace(day=1), today)
        slipping = overdue.sorted(lambda m: -m.delay_days)[:10]
        return {
            "subtitle": _("Every order's milestones against plan"),
            "headline": [{"t": self._n(len(overdue), _("milestone"), _("milestones")), "tone": "bad" if overdue else "b"},
                         _(" is overdue; on-time completion is ") if len(overdue) == 1
                         else _(" are overdue; on-time completion is "), {"t": "%s%%" % this_month, "tone": "b"},
                         _(" this month.")],
            "tiles": [
                self._tile("open", _("Milestones open"), len(open_ms), "", M, [("id", "in", open_ms.ids)]),
                self._tile("overdue", _("Overdue"), len(overdue), "bad" if overdue else "good",
                           M, [("id", "in", overdue.ids)]),
                self._tile("due_week", _("Due this week"), len(due_week), "warn", M, [("id", "in", due_week.ids)]),
                self._tile("on_time", _("On time this month"), this_month, "good" if this_month >= 80 else "warn",
                           M, [("actual_date", ">=", month_start)], fmt="pct"),
            ],
            "panels": [
                self._chart("on_time", _("On-time share by month"), "bar", labels,
                            [{"label": _("On time %"), "values": [on_time_share(a, b) for a, b in buckets],
                              "color": GREEN}], value_labels=True, legend=False),
                self._tbl("slipping", _("Milestones slipping"),
                            [(_("Order"), "start"), (_("Milestone"), "start"), (_("Planned"), "start"),
                             (_("Owner"), "start"), (_("Late by"), "end")],
                            [{"id": m.id, "tone": "bad" if m.delay_days > 5 else "",
                              "cells": [m.order_id.name, m.name, self._d(m.planned_date),
                                        m.owner_id.name or "", _("%s d", m.delay_days)]} for m in slipping],
                            model=M),
            ],
        }

    def _cockpit_fabric(self):
        """Screen 10. Rolls on the racks and what is holding them."""
        Lot, I, B = "stock.lot", "garment.fabric.inspection", "garment.fabric.booking"
        today = self._today()
        rolls = self.env[Lot].search(self._scope(Lot, [("roll_status", "!=", False)]))
        received = rolls.filtered(lambda r: r.roll_status == "received")
        to_inspect = received.filtered(lambda r: not r.roll_inspection_count)
        hold = rolls.filtered(lambda r: r.roll_status == "hold")
        month_start = today.replace(day=1)
        rej_dom = self._scope(I, [("result", "=", "reject"), ("date_inspected", ">=", month_start)])
        short = self.env[B].search(self._scope(B, [("state", "!=", "in_house")])).filtered("is_short")
        counts = {"approved": len(rolls.filtered(lambda r: r.roll_status == "approved")),
                  "received": len(received) - len(to_inspect), "to_inspect": len(to_inspect),
                  "hold": len(hold), "rejected": len(rolls.filtered(lambda r: r.roll_status == "rejected"))}
        by_supplier = self.env[I]._read_group(
            self._scope(I, [("result", "=", "reject"), ("date_inspected", ">=", today - timedelta(days=89))]),
            ["supplier_id"], ["__count"])
        by_supplier = sorted(by_supplier, key=lambda r: -r[1])[:8]
        return {
            "subtitle": _("Rolls on the racks and what is holding them"),
            "headline": [{"t": "{:,}".format(len(rolls)), "tone": "b"}, _(" rolls on hand; "),
                         {"t": _("%s wait for inspection", len(to_inspect)), "tone": "warn" if to_inspect else "b"},
                         _(" and "), {"t": _("%s are on hold", len(hold)), "tone": "bad" if hold else "b"}, "."],
            "tiles": [
                self._tile("on_hand", _("Rolls on hand"), len(rolls), "", Lot, [("id", "in", rolls.ids)]),
                self._tile("to_inspect", _("To inspect"), len(to_inspect), "warn" if to_inspect else "good",
                           Lot, [("id", "in", to_inspect.ids)]),
                self._tile("hold", _("On hold"), len(hold), "bad" if hold else "good", Lot, [("id", "in", hold.ids)]),
                self._tile("rejected", _("Rejected this month"), self._count(I, rej_dom), "bad", I, rej_dom),
                self._tile("short", _("Short bookings"), len(short), "warn" if short else "good",
                           B, [("id", "in", short.ids)]),
            ],
            "panels": [
                self._donut("status", _("Rolls by status"), [
                    {"label": _("Approved"), "value": counts["approved"], "color": VIOLET},
                    {"label": _("Received"), "value": counts["received"], "color": GREEN},
                    {"label": _("To inspect"), "value": counts["to_inspect"], "color": AMBER},
                    {"label": _("On hold"), "value": counts["hold"], "color": BLUE},
                    {"label": _("Rejected"), "value": counts["rejected"], "color": PINK}]),
                self._hbars("suppliers", _("Rejects by supplier, 90 days"),
                            [{"label": s.display_name or _("Unknown"), "value": n, "text": _("%s rolls", "%.1f" % n),
                              "tone": "violet"} for s, n in by_supplier]),
            ],
        }

    def _cockpit_cutting(self):
        """Screen 11. Cut against plan, marker efficiency and fabric use."""
        L, P, Order = "garment.lay", "garment.cut.plan", "garment.order"
        today = self._today()
        plan_dom = self._scope(P, [("state", "not in", ("draft", "cancel"))])
        t = self._sum(P, plan_dom, ["qty_to_cut", "qty_cut"])
        cut_dom = self._scope(L, [("state", "in", ("cut", "bundled"))])
        cut_lays = self.env[L].search(cut_dom)
        marker = round(sum(cut_lays.mapped("marker_efficiency")) / len(cut_lays), 1) if cut_lays else 0.0
        laid = sum(cut_lays.mapped("fabric_laid"))
        end_loss = round(sum(l.end_loss_pct * l.fabric_laid for l in cut_lays) / laid, 1) if laid else 0.0
        util = self._fabric_utilisation()
        table_dom = self._scope(L, [("state", "=", "spread")])
        vs_plan = round(self._pct(t["qty_cut"], t["qty_to_cut"], 0))
        labels, buckets = self._buckets()
        per = [0] * len(buckets)
        for lay in cut_lays.filtered(lambda l: l.cut_date and l.cut_date >= self._period_start()):
            i = self._bucket_of(buckets, lay.cut_date)
            if i is not None:
                per[i] += lay.pieces
        near = self.env[Order].search(self._open_orders_domain() + [
            ("ex_factory_date", "<=", today + timedelta(days=30))], order="ex_factory_date").filtered(
            lambda o: o.qty_cut < o.qty_ordered)
        return {
            "subtitle": _("Cut against plan, marker efficiency and fabric use"),
            "headline": [{"t": "{:,}".format(t["qty_cut"]), "tone": "b"}, _(" pieces cut against a plan of "),
                         {"t": "{:,}".format(t["qty_to_cut"]), "tone": "b"}, _("; fabric utilisation is "),
                         {"t": "%s%%" % util, "tone": "b"}, "."],
            "tiles": [
                self._tile("vs_plan", _("Cut vs plan"), vs_plan, "good" if vs_plan >= 95 else "warn", P, plan_dom,
                           fmt="pct"),
                self._tile("marker", _("Marker efficiency"), marker, "", L, cut_dom, fmt="pct"),
                self._tile("util", _("Fabric utilisation"), util, "good" if util >= 85 else "warn", L, cut_dom,
                           fmt="pct"),
                self._tile("end_loss", _("End loss"), end_loss, "warn" if end_loss > 2 else "good", L, cut_dom,
                           fmt="pct"),
                self._tile("on_table", _("Lays on table"), self._count(L, table_dom), "", L, table_dom),
            ],
            "panels": [
                self._chart("by_day", _("Pieces cut by day"), "bar", labels,
                            [{"label": _("Pieces cut"), "values": per, "color": VIOLET}], legend=False),
                self._tbl("near", _("Orders near ship date not fully cut"),
                            [(_("Order"), "start"), (_("Style"), "start"), (_("Ex-factory"), "start"),
                             (_("Cut"), "start")],
                            [{"id": o.id, "cells": [o.name, o.style_id.display_name or "", self._d(o.ex_factory_date),
                                                    {"pct": round(self._pct(o.qty_cut, o.qty_ordered, 0)),
                                                     "tone": "warn"}]} for o in near[:10]],
                            model=Order),
            ],
        }

    def _cockpit_capacity(self):
        """Screen 12. Standard minutes booked against what each line can sew, next 8 weeks."""
        P, Line = "garment.line.plan", "garment.line"
        today = self._today()
        monday = today - timedelta(days=today.weekday())
        weeks = [(monday + timedelta(weeks=i), monday + timedelta(weeks=i, days=6)) for i in range(8)]
        end = weeks[-1][1]
        lines = self.env[Line].search(self._company_domain())
        plans = self.env[P].search(self._scope(P, [("date_end", ">=", monday), ("date_start", "<=", end)]))
        booked_week = [0.0] * 8
        booked_line = defaultdict(float)
        for plan in plans:
            if not (plan.date_start and plan.date_end):
                continue
            days = [plan.date_start + timedelta(days=i) for i in range((plan.date_end - plan.date_start).days + 1)]
            days = [d for d in days if d.weekday() < WORKING_DAYS_PER_WEEK] or days
            per_day = plan.minutes / len(days)
            for d in days:
                i = self._bucket_of(weeks, d)
                if i is not None:
                    booked_week[i] += per_day
                    booked_line[plan.line_id.id] += per_day
        cap_day = sum(lines.mapped("capacity_minutes"))
        cap_week = cap_day * WORKING_DAYS_PER_WEEK
        booked, capacity = sum(booked_week), cap_week * 8
        pct = round(self._pct(booked, capacity, 0))
        late = plans.filtered("is_late")
        n_orders = len(plans.order_id)
        n_late = len(late.order_id)

        def k(v):
            return ("%.0fk" % (v / 1000)) if v >= 10000 else "{:,}".format(round(v))

        rows = []
        for line in lines:
            lp = self._pct(booked_line[line.id], line.capacity_minutes * WORKING_DAYS_PER_WEEK * 8)
            rows.append({"label": line.name, "value": lp, "text": "%.1f%%" % lp,
                         "tone": "bad" if lp > 100 else "warn" if lp > 95 else "good"})
        return {
            "subtitle": _("Standard minutes booked against what each line can sew"),
            "headline": [{"t": _("%(late)s of %(all)s", late=n_late, all=n_orders), "tone": "bad" if n_late else "b"},
                         _(" planned orders finish sewing after their ex-factory date.")],
            "tiles": [
                self._tile("booked", _("Booked minutes, 8 wks"), round(booked), "", P, [("id", "in", plans.ids)],
                           display=k(booked)),
                self._tile("capacity", _("Line capacity"), capacity, "", Line, [], display=k(capacity)),
                self._tile("pct", _("Booked"), pct, "bad" if pct > 100 else "warn" if pct > 95 else "good",
                           P, [("id", "in", plans.ids)], fmt="pct"),
                self._tile("late", _("Finishing late"), n_late, "bad" if n_late else "good", P, [("id", "in", late.ids)]),
            ],
            "panels": [
                self._chart("weeks", _("Booked minutes against capacity, next 8 weeks"), "bar",
                            ["Wk %s" % w[0].isocalendar()[1] for w in weeks],
                            [{"label": _("Booked (k min)"), "values": [round(b / 1000, 1) for b in booked_week],
                              "color": VIOLET},
                             {"label": _("Capacity (k min)"), "values": [round(cap_week / 1000, 1)] * 8,
                              "color": LIGHT}]),
                self._hbars("lines", _("Booked % by line"), rows, scale=max([100] + [r["value"] for r in rows]) * 1.15),
            ],
        }

    def _cockpit_jobwork(self):
        """Screen 13. Pieces out with subcontractors."""
        J = "garment.jobwork.order"
        today = self._today()
        out_dom = self._scope(J, [("state", "in", ("sent", "partly_received"))])
        jobs = self.env[J].search(out_dom)
        pending = sum(jobs.mapped("qty_pending"))
        late = jobs.filtered(lambda j: j.date_expected and j.date_expected < today)
        done = self.env[J].search(self._scope(J, [("state", "in", ("received", "billed", "partly_received"))]))
        sent = sum(done.mapped("qty_sent"))
        loss = round(sum(j.process_loss_pct * j.qty_sent for j in done) / sent, 1) if sent else 0.0
        procs = self.env[J]._fields["process"]._description_selection(self.env)
        order = ["print", "embroidery", "wash", "sewing"]
        procs = sorted(procs, key=lambda p: order.index(p[0]) if p[0] in order else 9)
        vendors = jobs.vendor_id
        series = [{"label": v.display_name, "color": SERIES[i % len(SERIES)],
                   "values": [sum(jobs.filtered(lambda j, v=v, p=p: j.vendor_id == v and j.process == p)
                                  .mapped("qty_pending")) for p, _l in procs]}
                  for i, v in enumerate(vendors)]
        names = {"print": _("Printing"), "embroidery": _("Embroidery"), "wash": _("Washing"), "sewing": _("Sewing")}
        return {
            "subtitle": _("Pieces out with subcontractors"),
            "headline": [{"t": "{:,}".format(pending), "tone": "b"}, _(" pieces are out; "),
                         {"t": _("%s job", len(late)) if len(late) == 1 else _("%s jobs", len(late)),
                          "tone": "bad" if late else "b"},
                         _(" is past its return date.") if len(late) == 1 else _(" are past their return date.")],
            "tiles": [
                self._tile("pending", _("Pieces out"), pending, "", J, out_dom),
                self._tile("out", _("Jobs open"), len(jobs), "", J, out_dom),
                self._tile("late", _("Late returns"), len(late), "bad" if late else "good", J, [("id", "in", late.ids)]),
                self._tile("loss", _("Process loss"), loss, "good" if loss <= 2 else "warn", J,
                           [("id", "in", done.ids)], fmt="pct"),
            ],
            "panels": [
                self._chart("process", _("Pieces out by process and vendor"), "bar",
                            [names.get(p, l) for p, l in procs], series, stacked=True),
                self._tbl("late", _("Late returns"),
                            [(_("Job"), "start"), (_("Vendor"), "start"), (_("Process"), "start"),
                             (_("Expected"), "start"), (_("Pending"), "end")],
                            [{"id": j.id, "tone": "bad",
                              "cells": [j.name, j.vendor_id.display_name or "", names.get(j.process, j.process),
                                        self._d(j.date_expected), "{:,}".format(j.qty_pending)]}
                             for j in late.sorted("date_expected")[:10]], model=J),
            ],
        }

    def _cockpit_quality(self):
        """Screen 14. Defects per hundred units and the inspections that block shipments."""
        I, D, C, Order = "garment.inspection", "garment.inspection.defect", "garment.capa", "garment.order"
        today = self._today()
        start = self._period_start()
        limit = self._dhu_limit()
        dhu = self._dhu(today)
        period_dom = [("date", ">=", fields.Datetime.to_string(start))]
        sev = dict(self.env[D]._read_group(self._scope(D, period_dom), ["severity"], ["qty:sum"]))
        block_dom = self._scope(Order, [("final_inspection_state", "=", "failed"),
                                        ("state", "not in", ("shipped", "closed", "cancel"))])
        n_block = self._count(Order, block_dom)
        capa_dom = self._scope(C, [("state", "in", ("open", "in_progress")), ("due_date", "<", today)])
        insp = self.env[I]._read_group(self._scope(I, [("kind", "=", "inline")] + period_dom), ["date:day"],
                                       ["defect_count:sum", "pieces_checked:sum"])
        per_day = defaultdict(lambda: [0, 0])
        for d, defects, pieces in insp:
            if d:
                k = d.date() if hasattr(d, "hour") else d
                per_day[k][0] += defects
                per_day[k][1] += pieces
        days = [start + timedelta(days=i) for i in range(self._days())]
        values = [self._pct(*per_day[d]) if per_day[d][1] else None for d in days]
        return {
            "subtitle": _("Defects per hundred units and the inspections that block shipments"),
            "headline": [_("DHU is "), {"t": "%s%%" % dhu, "tone": "b"}, _(" today against a limit of "),
                         {"t": "%s%%" % limit, "tone": "b"}, "; ",
                         {"t": _("%s final inspection", n_block) if n_block == 1
                          else _("%s final inspections", n_block), "tone": "bad" if n_block else "b"},
                         _(" blocks a shipment.") if n_block == 1 else _(" block shipments.")],
            "tiles": [
                self._tile("dhu", _("DHU today"), dhu, "bad" if dhu > limit else "warn" if dhu >= 0.8 * limit else "good",
                           I, [("kind", "=", "inline")], fmt="pct"),
                self._tile("limit", _("DHU limit"), limit, "", I, [("kind", "=", "inline")], fmt="pct"),
                self._tile("major", _("Major defects"), sev.get("major", 0), "warn" if sev.get("major") else "good",
                           D, self._scope(D, period_dom + [("severity", "=", "major")])),
                self._tile("blocking", _("Finals blocking"), n_block, "bad" if n_block else "good", Order, block_dom),
                self._tile("capa", _("CAPAs overdue"), self._count(C, capa_dom), "bad", C, capa_dom),
            ],
            "panels": [
                self._chart("dhu", _("Daily DHU against the limit"), "line", [d.strftime("%d/%m") for d in days],
                            [{"label": _("DHU %"), "values": values, "color": VIOLET}], ref=limit),
                self._donut("severity", _("Defects by severity"), [
                    {"label": _("Minor"), "value": sev.get("minor", 0), "color": GREY},
                    {"label": _("Major"), "value": sev.get("major", 0), "color": AMBER},
                    {"label": _("Critical"), "value": sev.get("critical", 0), "color": RED}]),
            ],
        }

    def _cockpit_shipping(self):
        """Screen 15. Packing, cartons, shipments and letters of credit."""
        Ca, Sh, Order = "garment.carton", "garment.shipment", "garment.order"
        packed = self._sum(Order, self._open_orders_domain(), ["qty_packed"])["qty_packed"]
        cartons = self.env[Ca].search(self._scope(Ca, [("state", "in", ("packed", "shipped"))]))
        ready = cartons.filtered(lambda c: c.state == "packed")
        open_dom = self._scope(Sh, [("stage", "!=", "paid")])
        shipments = self.env[Sh].search(open_dom, order="planned_date")
        late = shipments.filtered(lambda s: s.days_late > 0)
        lcs = self._expiring_lcs(7)
        stages = dict(self.env[Sh]._fields["stage"]._description_selection(self.env))
        return {
            "subtitle": _("Packing, cartons, shipments and letters of credit"),
            "headline": [{"t": "{:,}".format(packed), "tone": "b"}, _(" pieces packed; "),
                         {"t": _("%s shipment", len(late)) if len(late) == 1 else _("%s shipments", len(late)),
                          "tone": "bad" if late else "b"},
                         _(" is late and ") if len(late) == 1 else _(" are late and "),
                         {"t": _("%s LC", len(lcs)) if len(lcs) == 1 else _("%s LCs", len(lcs)),
                          "tone": "warn" if lcs else "b"},
                         _(" expires within 7 days.") if len(lcs) == 1 else _(" expire within 7 days.")],
            "tiles": [
                self._tile("packed_pcs", _("Packed"), packed, "", Order, self._open_orders_domain()),
                self._tile("packed", _("Cartons ready"), len(ready), "", Ca, [("id", "in", ready.ids)]),
                self._tile("open", _("Shipments open"), len(shipments), "", Sh, open_dom),
                self._tile("late", _("Late shipments"), len(late), "bad" if late else "good", Sh, [("id", "in", late.ids)]),
                self._tile("lcs", _("LCs expiring"), len(lcs), "warn" if lcs else "good", "garment.lc",
                           [("id", "in", lcs.ids)]),
            ],
            "panels": [
                self._donut("cartons", _("Cartons by status"), [
                    {"label": _("Packed"), "value": len(ready.filtered(lambda c: not c.stock_posted)), "color": VIOLET},
                    {"label": _("Posted to stock"), "value": len(ready.filtered("stock_posted")), "color": GREEN},
                    {"label": _("Shipped"), "value": len(cartons) - len(ready), "color": AMBER}]),
                self._tbl("shipments", _("Shipments by stage"),
                            [(_("Shipment"), "start"), (_("Buyer"), "start"), (_("Stage"), "start"),
                             (_("Ex-factory"), "start"), (_("Late"), "end")],
                            [{"id": s.id, "cells": [s.name, s.buyer_id.display_name or "",
                                                    {"badge": stages.get(s.stage, s.stage),
                                                     "tone": "violet" if s.stage not in ("draft", "confirmed") else ""},
                                                    self._d(s.planned_date),
                                                    _("%s d", s.days_late) if s.days_late > 0 else "—"]}
                             for s in shipments[:10]], model=Sh),
            ],
        }

    def _cockpit_wages(self):
        """Screen 16. Piece-rate earnings, top-ups and the cost of a standard minute (latest wage week)."""
        W, WL = "garment.wage.sheet", "garment.wage.sheet.line"
        dom = self._scope(W, [("state", "!=", "cancel")])
        latest = self.env[W].search(dom, order="date_from desc", limit=1)
        week = self.env[W].search(dom + [("date_from", "=", latest.date_from)]) if latest else self.env[W]
        lines = week.line_ids
        topped = lines.filtered(lambda l: l.topup > 0)
        earn, topup = sum(lines.mapped("piece_earnings")), sum(lines.mapped("topup"))
        incentive, overtime = sum(lines.mapped("incentive")), sum(lines.mapped("overtime_pay"))
        gross = earn + topup + incentive + overtime
        minutes = sum(lines.mapped("minutes_earned"))
        per_min = round(gross / minutes, 2) if minutes else 0.0
        div, unit = self._money_unit()
        labels, buckets = self._buckets() if self._days() > 31 else self._weeks_back(5)
        per = [0.0] * len(buckets)
        for sheet in self.env[W].search(dom + [("date_from", ">=", buckets[0][0])]):
            i = self._bucket_of(buckets, sheet.date_from)
            if i is not None:
                per[i] += sum(sheet.line_ids.mapped(lambda l: l.piece_earnings + l.topup + l.incentive + l.overtime_pay))
        top = lines.sorted(lambda l: -l.net_payable)[:5]
        sym = self.env.company.currency_id.symbol or ""
        week_dom = [("id", "in", week.ids)]
        return {
            "subtitle": _("Piece-rate earnings, top-ups and the cost of a standard minute"),
            "headline": [_("This week's gross wages are "), {"t": self._money(gross, short=False), "tone": "b"}, "; ",
                         {"t": self._n(len(topped), _("operator"), _("operators")), "tone": "warn" if topped else "b"},
                         _(" needed a top-up to the minimum.")],
            "tiles": [
                self._tile("gross", _("Gross wages"), gross, "", W, week_dom, fmt="money", display=self._money(gross)),
                self._tile("topup", _("Minimum top-up"), topup, "warn" if topup else "good", WL,
                           [("id", "in", topped.ids)], fmt="money", display=self._money(topup)),
                self._tile("incentive", _("Incentives"), incentive, "", W, week_dom, fmt="money",
                           display=self._money(incentive)),
                self._tile("overtime", _("Overtime"), overtime, "", W, week_dom, fmt="money",
                           display=self._money(overtime)),
                self._tile("per_min", _("Cost / std minute"), per_min, "", W, week_dom, fmt="money",
                           display="%s%.2f" % (sym, per_min)),
            ],
            "panels": [
                self._chart("weeks", _("Wages by week"), "bar", labels,
                            [{"label": _("Gross wages (%s)", unit), "values": [round(v / div, 1) for v in per],
                              "color": VIOLET}], value_labels=True, legend=False, unit=unit),
                self._tbl("top", _("Efficiency vs earnings, top operators"),
                            [(_("Badge"), "start"), (_("Operator"), "start"), (_("Efficiency"), "end"),
                             (_("Earnings"), "end")],
                            [{"id": l.id, "cells": [l.badge or "", l.employee_id.name or "", "%.1f%%" % l.efficiency,
                                                    self._money(l.net_payable, short=False)]} for l in top],
                            model=WL),
            ],
        }

    def _weeks_back(self, n):
        today = self._today()
        monday = today - timedelta(days=today.weekday())
        weeks = [(monday - timedelta(weeks=i), monday - timedelta(weeks=i) + timedelta(days=6))
                 for i in range(n - 1, -1, -1)]
        return ["Wk %s" % w[0].isocalendar()[1] for w in weeks], weeks

    def _cockpit_profit(self):
        """Screen 17. What each order really made (closed orders, at least the last 90 days)."""
        P = "garment.order.pnl"
        days = max(self._days(), 90)
        dom = self._scope(P, [("is_closed", "=", True),
                              ("date_ex_factory", ">=", self._today() - timedelta(days=days - 1))])
        s = self.env[P]._garment_profit_summary(dom)
        loss = s["loss_orders"]
        margin, vs_plan = round(s["margin_pct"], 1), round(s["cost_vs_plan_pct"], 1)
        n_loss = s["loss_count"]
        return {
            "subtitle": _("What each order really made"),
            "headline": [_("Closed orders made "), {"t": "%s%%" % margin, "tone": "b"}, _(" on average; "),
                         {"t": _("%s order", n_loss) if n_loss == 1 else _("%s orders", n_loss),
                          "tone": "bad" if n_loss else "b"}, _(" lost money.")],
            "tiles": [
                self._tile("revenue", _("Revenue, %s days", days), s["revenue"], "", P, dom, fmt="money",
                           display=self._money(s["revenue"])),
                self._tile("cost", _("Actual cost"), s["actual_cost"], "", P, dom, fmt="money",
                           display=self._money(s["actual_cost"])),
                self._tile("margin", _("Margin"), margin, "good" if margin > 0 else "bad", P, dom, fmt="pct"),
                self._tile("vs_plan", _("Cost vs plan"), vs_plan, "warn" if vs_plan > 0 else "good", P, dom,
                           fmt="pct", display="%+.1f%%" % vs_plan),
                self._tile("loss", _("Loss-making orders"), n_loss, "bad" if n_loss else "good",
                           P, dom + [("is_loss", "=", True)]),
            ],
            "panels": [
                self._hbars("buyers", _("Margin by buyer"),
                            [{"label": b["buyer"] or _("None"), "value": max(b["margin_pct"], 0),
                              "text": "%.1f%%" % b["margin_pct"], "tone": "violet" if b["margin_pct"] >= 0 else "bad"}
                             for b in s["margin_by_buyer"]]),
                self._tbl("loss", _("Loss-making orders"),
                            [(_("Order"), "start"), (_("Style"), "start"), (_("Revenue"), "end"),
                             (_("Cost"), "end"), (_("Margin"), "end")],
                            [{"id": p.id, "tone": "bad",
                              "cells": [p.order_id.name or p.name, p.style_id.display_name or "",
                                        self._money(p.revenue, short=False), self._money(p.actual_cost, short=False),
                                        "%.1f%%" % p.margin_pct]} for p in loss[:10]], model=P),
            ],
        }
