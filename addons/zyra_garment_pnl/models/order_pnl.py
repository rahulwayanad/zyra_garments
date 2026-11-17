from collections import defaultdict

from odoo import _, api, fields, models
from odoo.tools import float_round

FIGURES = (
    "qty_ordered", "qty_shipped", "pieces_costed", "order_value", "revenue",
    "planned_material", "planned_making", "planned_other", "planned_cost", "planned_margin_pct",
    "actual_material", "actual_making", "actual_jobwork", "actual_other", "actual_cost",
    "cost_variance", "margin", "margin_pct", "revenue_pc", "cost_pc", "margin_pc",
)


class GarmentOrderPnl(models.Model):
    _name = "garment.order.pnl"
    _description = "Order P&L"
    _inherit = ["mail.thread"]
    _order = "date_ex_factory desc, id desc"
    _rec_name = "name"

    name = fields.Char(compute="_compute_name", store=True)
    order_id = fields.Many2one("garment.order", string="Order", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    buyer_id = fields.Many2one(related="order_id.buyer_id", store=True, string="Buyer")
    style_id = fields.Many2one(related="order_id.style_id", store=True, string="Style")
    business_model = fields.Selection(related="order_id.business_model", store=True, string="Business Model")
    order_state = fields.Selection(related="order_id.state", store=True, string="Order State")
    order_status = fields.Char(compute="_compute_order_info", store=True, string="Order Status")
    is_closed = fields.Boolean(compute="_compute_order_info", store=True,
                               help="Order shipped or closed: its figures are final.")
    date_ex_factory = fields.Date(related="order_id.ex_factory_date", store=True, string="Ex-Factory Date")
    cost_sheet_ref = fields.Char(string="Cost Sheet", readonly=True)
    last_refresh = fields.Datetime(readonly=True)

    # pieces
    qty_ordered = fields.Integer(string="Ordered", readonly=True)
    qty_shipped = fields.Integer(string="Shipped", readonly=True)
    pieces_costed = fields.Integer(string="Pieces Costed", readonly=True, aggregator="sum",
                                   help="Shipped pieces; the ordered pieces while nothing has shipped.")
    # revenue
    order_value = fields.Monetary(readonly=True)
    revenue = fields.Monetary(string="Invoiced", readonly=True,
                              help="Posted customer invoices and credit notes of the order.")
    # planned (approved cost sheet × pieces costed)
    planned_material = fields.Monetary(readonly=True)
    planned_making = fields.Monetary(readonly=True)
    planned_other = fields.Monetary(readonly=True)
    planned_cost = fields.Monetary(readonly=True)
    planned_margin_pct = fields.Float(string="Planned Margin %", readonly=True, digits=(16, 2), aggregator="avg")
    # actual
    actual_material = fields.Monetary(string="Material", readonly=True)
    actual_making = fields.Monetary(string="Making (Wages)", readonly=True)
    actual_jobwork = fields.Monetary(string="Job Work", readonly=True)
    actual_other = fields.Monetary(string="Other Cost", readonly=True)
    actual_cost = fields.Monetary(readonly=True)
    cost_variance = fields.Monetary(readonly=True, help="Actual cost − planned cost (positive = over plan).")
    margin = fields.Monetary(readonly=True)
    margin_pct = fields.Float(string="Margin %", readonly=True, digits=(16, 2), aggregator="avg")
    margin_ratio = fields.Float(compute="_compute_margin_ratio", store=True, string="Margin Ratio",
                                aggregator="avg", help="Margin % ÷ 100, for the percentage widget.")
    revenue_pc = fields.Monetary(string="Revenue / pc", readonly=True, aggregator="avg")
    cost_pc = fields.Monetary(string="Cost / pc", readonly=True, aggregator="avg")
    margin_pc = fields.Monetary(string="Margin / pc", readonly=True, aggregator="avg")
    is_loss = fields.Boolean(string="Loss-making", readonly=True)

    cost_line_ids = fields.One2many("garment.order.pnl.cost", "pnl_id", string="Other Costs")

    _sql_constraints = [("order_unique", "unique(order_id)", "An order has one P&L.")]

    @api.depends("margin_pct")
    def _compute_margin_ratio(self):
        for rec in self:
            rec.margin_ratio = rec.margin_pct / 100.0

    @api.depends("order_id.name", "order_id.style_id.code")
    def _compute_name(self):
        for rec in self:
            code = rec.order_id.style_id.code
            rec.name = "%s · %s" % (rec.order_id.name, code) if code else rec.order_id.name

    @api.depends("order_id.state")
    def _compute_order_info(self):
        labels = dict(self.env["garment.order"]._fields["state"]._description_selection(self.env))
        for rec in self:
            state = rec.order_id.state
            rec.is_closed = state in ("shipped", "closed")
            rec.order_status = _("Closed") if state == "closed" else labels.get(state, "")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_refresh()
        return records

    # ------------------------------------------------------------------ formulas
    @api.model
    def _pnl_figures(self, src):
        """Order P&L from its raw amounts (all money in company currency).

        src: pieces_costed, qty_ordered, qty_shipped, order_value, revenue, planned_material_pc,
        planned_making_pc, planned_other_pc, material, making, jobwork, other.
        Planned cost = cost sheet per piece × pieces costed; variance = actual − planned;
        margin = invoiced − actual; margin % and planned margin % are shares of the invoiced revenue.
        """
        pieces = src.get("pieces_costed") or 0
        revenue = src.get("revenue") or 0.0
        planned_material = (src.get("planned_material_pc") or 0.0) * pieces
        planned_making = (src.get("planned_making_pc") or 0.0) * pieces
        planned_other = (src.get("planned_other_pc") or 0.0) * pieces
        planned = planned_material + planned_making + planned_other
        actual = sum(src.get(k) or 0.0 for k in ("material", "making", "jobwork", "other"))
        margin = revenue - actual

        def pct(value):
            return float_round(value / revenue * 100.0, 2) if revenue else 0.0

        def per_pc(value):
            return value / pieces if pieces else 0.0

        return {
            "qty_ordered": src.get("qty_ordered") or 0,
            "qty_shipped": src.get("qty_shipped") or 0,
            "pieces_costed": pieces,
            "order_value": src.get("order_value") or 0.0,
            "revenue": revenue,
            "planned_material": planned_material,
            "planned_making": planned_making,
            "planned_other": planned_other,
            "planned_cost": planned,
            "planned_margin_pct": pct(revenue - planned) if planned else 0.0,
            "actual_material": src.get("material") or 0.0,
            "actual_making": src.get("making") or 0.0,
            "actual_jobwork": src.get("jobwork") or 0.0,
            "actual_other": src.get("other") or 0.0,
            "actual_cost": actual,
            "cost_variance": actual - planned,
            "margin": margin,
            "margin_pct": pct(margin),
            "revenue_pc": per_pc(revenue),
            "cost_pc": per_pc(actual),
            "margin_pc": per_pc(margin),
            "is_loss": margin < 0,
        }

    # ------------------------------------------------------------------ sources
    def _src_revenue(self, order):
        """Posted customer invoice lines of the order: lines tagged with the order, plus the shipment
        invoices' lines written for the order (shipping names them after the order)."""
        Line = self.env["account.move.line"].sudo()
        lines = Line.search([("garment_order_id", "=", order.id), ("parent_state", "=", "posted"),
                             ("move_id.move_type", "in", ("out_invoice", "out_refund")),
                             ("display_type", "=", "product")])
        invoices = order.shipment_ids.invoice_ids.filtered(
            lambda m: m.state == "posted" and m.move_type in ("out_invoice", "out_refund"))
        prefix = order.display_name + " · "
        lines |= invoices.invoice_line_ids.filtered(
            lambda li: not li.garment_order_id and li.display_type == "product"
            and (li.name or "").startswith(prefix))
        return -sum(lines.mapped("balance"))

    def _src_material(self, order):
        """Stock value of done moves consuming material for the order: fabric cut on its lays and
        material issued to the order (stock.move.garment_pnl_order_id); returns to stock reduce it."""
        Move = self.env["stock.move"].sudo()
        domain = [("state", "=", "done"), "|", ("garment_pnl_order_id", "=", order.id),
                  ("garment_lay_id.order_id", "=", order.id)]
        total = 0.0
        for move in Move.search(domain):
            layers = move.stock_valuation_layer_ids
            if layers:
                total -= sum(layers.mapped("value"))
            else:
                sign = -1 if move.location_dest_id.usage == "internal" else 1
                total += sign * move.quantity * move.product_id.standard_price
        return total

    def _src_making(self, order):
        """Wages paid for the order: each wage line's net pay shared by its minutes on the order's scans.
        Cancelled sheets release their scans and count nothing."""
        scans = self.env["garment.scan"].sudo().search([("order_id", "=", order.id), ("wage_line_id", "!=", False)])
        by_line = defaultdict(float)
        for scan in scans:
            by_line[scan.wage_line_id] += scan.minutes_earned
        total = 0.0
        for line, minutes in by_line.items():
            if line.sheet_id.state == "cancel" or not line.minutes_earned:
                continue
            total += line.net_payable * minutes / line.minutes_earned
        return total

    def _src_jobwork(self, order):
        """Job work of the order: posted vendor bills of its job-work purchase orders; a PO not billed
        yet counts at its untaxed amount (committed)."""
        jobs = self.env["garment.jobwork.order"].sudo().search([("production_order_id", "=", order.id)])
        total = 0.0
        for po in jobs.purchase_ids.filtered(lambda p: p.state in ("purchase", "done")):
            bill_lines = po.order_line.invoice_lines.filtered(lambda li: li.parent_state == "posted")
            if bill_lines:
                total += sum(bill_lines.mapped("balance"))
            else:
                total += po.currency_id._convert(po.amount_untaxed, order.company_id.currency_id,
                                                 order.company_id, fields.Date.context_today(self))
        return total

    def _src_other(self, order):
        """Other costs typed on the P&L plus sample costs of the order not charged to the buyer."""
        total = sum(self.cost_line_ids.mapped("amount"))
        if "garment.sample" in self.env:
            samples = self.env["garment.sample"].sudo().search([("order_id", "=", order.id),
                                                                 ("charge_to_buyer", "=", False)])
            total += sum(samples.mapped("cost"))
        return total

    def _sources(self):
        self.ensure_one()
        order = self.order_id.sudo()
        shipped = order.qty_shipped
        return {
            "qty_ordered": order.qty_ordered,
            "qty_shipped": shipped,
            "pieces_costed": shipped or order.qty_ordered,
            "order_value": order.order_value,
            "revenue": self._src_revenue(order),
            "planned_material_pc": order.planned_material_pc,
            "planned_making_pc": order.planned_making_pc,
            "planned_other_pc": order.planned_other_pc,
            "material": self._src_material(order),
            "making": self._src_making(order),
            "jobwork": self._src_jobwork(order),
            "other": self._src_other(order),
        }

    def action_refresh(self):
        for rec in self:
            vals = rec._pnl_figures(rec._sources())
            sheet = rec.order_id.sudo().cost_sheet_ref
            vals["cost_sheet_ref"] = sheet.display_name if sheet else False
            vals["last_refresh"] = fields.Datetime.now()
            rec.sudo().write(vals)
        return True

    @api.model
    def _cron_refresh(self):
        """Nightly: every open order gets a P&L, closed ones keep theirs up to date."""
        orders = self.env["garment.order"].sudo().search([("state", "not in", ("draft", "cancel"))])
        orders._garment_pnl()

    # ------------------------------------------------------------------ cockpit helper
    @api.model
    def _garment_profit_summary(self, domain=None):
        """Totals for the profit cockpit over the P&L records matching domain (default: closed orders)."""
        recs = self.search(domain if domain is not None else [("is_closed", "=", True)])
        revenue = sum(recs.mapped("revenue"))
        cost = sum(recs.mapped("actual_cost"))
        planned = sum(recs.mapped("planned_cost"))
        by_buyer = defaultdict(lambda: [0.0, 0.0])
        for rec in recs:
            by_buyer[rec.buyer_id][0] += rec.revenue
            by_buyer[rec.buyer_id][1] += rec.margin
        return {
            "revenue": revenue,
            "actual_cost": cost,
            "margin_pct": (revenue - cost) / revenue * 100 if revenue else 0.0,
            "cost_vs_plan_pct": (cost - planned) / planned * 100 if planned else 0.0,
            "loss_count": len(recs.filtered("is_loss")),
            "loss_orders": recs.filtered("is_loss"),
            "margin_by_buyer": [
                {"buyer": b.display_name, "buyer_id": b.id, "margin_pct": m / r * 100 if r else 0.0}
                for b, (r, m) in by_buyer.items()
            ],
        }


class GarmentOrderPnlCost(models.Model):
    _name = "garment.order.pnl.cost"
    _description = "Order P&L Other Cost"
    _order = "date, id"

    pnl_id = fields.Many2one("garment.order.pnl", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="pnl_id.company_id", store=True)
    currency_id = fields.Many2one(related="pnl_id.currency_id")
    date = fields.Date(default=fields.Date.context_today)
    name = fields.Char(string="Description", required=True)
    amount = fields.Monetary(required=True)
