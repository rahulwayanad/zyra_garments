from datetime import date

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

OPEN_STATES = ("confirmed", "in_production", "packed")
STAGES = [("ordered", "Ordered"), ("cut", "Cut"), ("sewn", "Sewn"), ("packed", "Packed"), ("shipped", "Shipped")]


def short_date(d):
    """'Oct 3' as on the screens; '—' when empty."""
    if not d:
        return "—"
    return "%s %s" % (d.strftime("%b"), d.day)


class GarmentPortal(http.Controller):
    """Buyer pages (screens 122–124 + approvals) and the job-work vendor page (screen 125).

    Every list is searched with the portal user's own environment, so the record rules of this module decide what is
    shown; only the display values of records already found are read with sudo (related styles, grid, T&A).
    """

    # ---------- helpers ----------
    def _partner(self):
        return request.env.user.partner_id.commercial_partner_id

    def _kind(self):
        if request.env.user._is_internal():
            return "buyer"
        return request.env.user.partner_id._garment_portal_kind()

    def _values(self, page, **kw):
        user = request.env.user
        initials = "".join(w[0] for w in (user.name or "?").split()[:2]).upper()
        company = request.env.company
        values = {
            "page": page,
            "kind": self._kind(),
            "portal_partner": self._partner(),
            "user_initials": initials,
            "company_name": company.name,
            "company_initials": "".join(w[0] for w in (company.name or "?").split()[:2]).upper(),
            "short_date": short_date,
            "fmt": lambda n: "{:,}".format(int(n or 0)),
            "no_header": True,
            "no_footer": True,
        }
        values.update(kw)
        return values

    def _order_status(self, order):
        if order.state in ("shipped", "closed"):
            return ("shipped", _("Shipped"))
        if order.is_late:
            return ("late", _("Late"))
        return ("on_track", _("On track"))

    def _get_order(self, order_id):
        order = request.env["garment.order"].browse(order_id)
        try:
            order.check_access("read")
            order.read(["name"])
        except (AccessError, MissingError):
            return None
        return order

    # ---------- buyer ----------
    @http.route(["/my/garment"], type="http", auth="user", website=False)
    def garment_home(self, **kw):
        if self._kind() == "vendor":
            return request.redirect("/my/garment/jobwork")
        Order = request.env["garment.order"]
        orders = Order.search([("state", "!=", "cancel")], order="ex_factory_date, id")
        open_orders = orders.filtered(lambda o: o.state in OPEN_STATES)
        today = fields.Date.context_today(Order)
        upcoming = [o.ex_factory_date for o in open_orders if o.ex_factory_date and o.ex_factory_date >= today]
        styles = request.env["garment.style"].search([], order="name")
        values = self._values(
            "home",
            orders=open_orders.sudo(),
            styles=styles.sudo(),
            kpi_open=len(open_orders),
            kpi_late=len(open_orders.filtered("is_late")),
            kpi_styles=len(styles),
            kpi_next=short_date(min(upcoming) if upcoming else None),
        )
        return request.render("zyra_garment_portal.portal_garment_home", values)

    @http.route(["/my/garment/orders"], type="http", auth="user", website=False)
    def garment_orders(self, **kw):
        orders = request.env["garment.order"].search([("state", "!=", "cancel")], order="id desc")
        orders = orders.sorted(lambda o: (o.state in ("shipped", "closed"), -(o.id)))
        return request.render("zyra_garment_portal.portal_garment_orders", self._values(
            "orders", orders=orders.sudo(), order_status=self._order_status))

    @http.route(["/my/garment/orders/<int:order_id>"], type="http", auth="user", website=False)
    def garment_order(self, order_id, **kw):
        order = self._get_order(order_id)
        if not order:
            raise request.not_found()
        order = order.sudo()
        grid = order._garment_get_grid()
        colours = order.colour_ids
        rows = []
        for key, label in STAGES:
            per_colour = [sum(v[key] for (c, s), v in grid.items() if c == colour.id) for colour in colours]
            rows.append({"label": label, "cells": per_colour, "total": sum(per_colour)})
        return request.render("zyra_garment_portal.portal_garment_order", self._values(
            "orders", order=order, colours=colours, rows=rows,
            milestones=order.milestone_ids.sorted(lambda m: (m.planned_date or date.max, m.id))))

    @http.route(["/my/garment/styles"], type="http", auth="user", website=False)
    def garment_styles(self, **kw):
        styles = request.env["garment.style"].search([], order="name")
        return request.render("zyra_garment_portal.portal_garment_styles", self._values(
            "styles", styles=styles.sudo()))

    @http.route(["/my/garment/approvals"], type="http", auth="user", website=False)
    def garment_approvals(self, message=None, **kw):
        samples = request.env["garment.sample"].search([("state", "=", "with_buyer")], order="sent_date, id")
        approvals = request.env["garment.approval"].search([("state", "=", "with_buyer")], order="sent_date, id")
        return request.render("zyra_garment_portal.portal_garment_approvals", self._values(
            "approvals", samples=samples.sudo(), approvals=approvals.sudo(), message=message))

    @http.route(["/my/garment/sample/<int:sample_id>/decide"], type="http", auth="user", methods=["POST"],
                website=False)
    def garment_sample_decide(self, sample_id, decision=None, comment=None, **kw):
        sample = request.env["garment.sample"].browse(sample_id)
        try:
            sample.check_access("read")
            sample.read(["name"])
        except (AccessError, MissingError):
            raise request.not_found()
        sample = sample.sudo()
        try:
            if comment:
                sample.buyer_comments = comment
            if decision == "approve":
                sample.action_approve()
            elif decision == "reject":
                sample.action_reject()
            if comment:
                sample.message_post(body=_("Buyer comment from the portal: %s", comment),
                                    author_id=request.env.user.partner_id.id)
        except UserError as e:
            return request.redirect("/my/garment/approvals?message=%s" % e.args[0])
        return request.redirect("/my/garment/approvals")

    @http.route(["/my/garment/approval/<int:approval_id>/decide"], type="http", auth="user", methods=["POST"],
                website=False)
    def garment_approval_decide(self, approval_id, decision=None, option_id=None, comment=None, **kw):
        card = request.env["garment.approval"].browse(approval_id)
        try:
            card.check_access("read")
            card.read(["name"])
        except (AccessError, MissingError):
            raise request.not_found()
        card = card.sudo()
        try:
            vals = {}
            if comment:
                vals["buyer_comment"] = comment
            if option_id and int(option_id) in card.option_ids.ids:
                vals["chosen_option_id"] = int(option_id)
            if vals:
                card.write(vals)
            if decision == "approve":
                card.action_approve()
            elif decision == "reject":
                card.action_ask_resubmission()
        except UserError as e:
            return request.redirect("/my/garment/approvals?message=%s" % e.args[0])
        return request.redirect("/my/garment/approvals")

    # ---------- job-work vendor ----------
    @http.route(["/my/garment/jobwork"], type="http", auth="user", website=False)
    def garment_jobwork(self, **kw):
        jobs = request.env["garment.jobwork.order"].search(
            [("state", "in", ("sent", "partly_received"))], order="date_expected, id")
        process_labels = dict(request.env["garment.jobwork.order"]._fields["process"]._description_selection(
            request.env))
        return request.render("zyra_garment_portal.portal_garment_jobwork", self._values(
            "jobwork", jobs=jobs.sudo(), process_labels=process_labels))
