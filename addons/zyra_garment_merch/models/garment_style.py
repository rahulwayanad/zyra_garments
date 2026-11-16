from odoo import api, fields, models


class GarmentStyle(models.Model):
    """Order figures on the style (screens 22–23). The style itself belongs to zyra_techpack."""

    _inherit = "garment.style"

    garment_order_ids = fields.One2many("garment.order", "style_id", string="Production Orders")
    order_count = fields.Integer(string="Orders", compute="_compute_merch_figures")
    open_order_count = fields.Integer(string="Open Orders", compute="_compute_merch_figures",
                                      help="Production orders not yet shipped, completed or cancelled.")
    pieces_on_order = fields.Integer(string="Pieces on Order", compute="_compute_merch_figures",
                                     help="Pieces ordered on the open production orders.")
    sample_count = fields.Integer(string="Samples", compute="_compute_merch_figures")
    samples_pending = fields.Integer(string="Samples Pending", compute="_compute_merch_figures",
                                     help="Samples not yet approved by the buyer.")
    approval_count = fields.Integer(string="Approvals", compute="_compute_merch_figures")
    approvals_pending = fields.Integer(string="Approvals Pending", compute="_compute_merch_figures",
                                       help="Approval cards not yet approved by the buyer.")
    has_costing = fields.Boolean(compute="_compute_price_left",
                                 help="zyra_garment_costing is installed: it shows its own Costed FOB tile.")
    costed_fob = fields.Monetary(string="FOB for Price Less Material", compute="_compute_price_left",
                                 currency_field="currency_id",
                                 help="FOB price of the approved cost sheet when costing is installed, "
                                      "otherwise the average price of the open production orders.")
    price_less_material = fields.Monetary(string="Price Less Material", compute="_compute_price_left",
                                          currency_field="currency_id",
                                          help="Costed FOB minus material cost per piece.")

    @api.depends("garment_order_ids.state", "garment_order_ids.qty_ordered")
    def _compute_merch_figures(self):
        Order = self.env["garment.order"]
        Sample = self.env["garment.sample"]
        Approval = self.env["garment.approval"]
        ids = [i for i in self.ids if isinstance(i, int)]
        orders_by_style = {}
        samples = {}
        approvals = {}
        if ids:
            for style, state, count, qty in Order._read_group(
                    [("style_id", "in", ids)], ["style_id", "state"], ["__count", "qty_ordered:sum"]):
                orders_by_style.setdefault(style.id, []).append((state, count, qty))
            for style, state, count in Sample._read_group(
                    [("style_id", "in", ids)], ["style_id", "state"], ["__count"]):
                samples.setdefault(style.id, []).append((state, count))
            for style, state, count in Approval._read_group(
                    [("style_id", "in", ids)], ["style_id", "state"], ["__count"]):
                approvals.setdefault(style.id, []).append((state, count))
        open_states = ("draft", "confirmed", "in_production", "packed")
        for style in self:
            rows = orders_by_style.get(style.id, [])
            style.order_count = sum(r[1] for r in rows if r[0] != "cancel")
            style.open_order_count = sum(r[1] for r in rows if r[0] in open_states)
            style.pieces_on_order = sum(r[2] for r in rows if r[0] in open_states)
            srows = samples.get(style.id, [])
            style.sample_count = sum(r[1] for r in srows)
            style.samples_pending = sum(r[1] for r in srows if r[0] != "approved")
            arows = approvals.get(style.id, [])
            style.approval_count = sum(r[1] for r in arows)
            style.approvals_pending = sum(r[1] for r in arows if r[0] != "approved")

    def _get_costed_fob(self):
        """FOB from the approved cost sheet (zyra_garment_costing, soft), else average open-order price."""
        self.ensure_one()
        if "costed_fob_price" in self._fields:
            fob = self.sudo().costed_fob_price
            if fob:
                return fob
        if "garment.cost.sheet" in self.env:
            Sheet = self.env["garment.cost.sheet"]
            domain = [("state", "=", "approved")]
            if "style_id" in Sheet._fields and Sheet._fields["style_id"].store:
                domain.append(("style_id", "=", self.id))
            elif "techpack_id" in Sheet._fields:
                domain.append(("techpack_id.style_id", "=", self.id))
            else:
                domain = None
            if domain:
                sheet = Sheet.search(domain, order="id desc", limit=1)
                for fname in ("fob_price", "fob", "price_fob"):
                    if sheet and fname in Sheet._fields:
                        return sheet[fname]
        orders = self.garment_order_ids.filtered(lambda o: o.state != "cancel" and o.price_unit)
        if orders:
            return sum(orders.mapped("price_unit")) / len(orders)
        return 0.0

    @api.depends("material_cost", "garment_order_ids.price_unit")
    def _compute_price_left(self):
        has_costing = "garment.cost.sheet" in self.env
        for style in self:
            style.has_costing = has_costing
            fob = style._get_costed_fob() if isinstance(style.id, int) else 0.0
            style.costed_fob = fob
            style.price_less_material = fob - style.material_cost if fob else 0.0

    def action_view_garment_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_order")
        action["domain"] = [("style_id", "=", self.id)]
        action["context"] = {"default_style_id": self.id}
        return action

    def action_view_samples(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_sample")
        action["domain"] = [("style_id", "=", self.id)]
        action["context"] = {"default_style_id": self.id}
        return action

    def action_view_approvals(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_merch.action_garment_approval")
        action["domain"] = [("style_id", "=", self.id)]
        action["context"] = {"default_style_id": self.id}
        return action
