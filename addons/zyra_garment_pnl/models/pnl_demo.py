from datetime import timedelta

from odoo import Command, api, fields, models

# (style code, qty per grid cell, price, shipped share, material ×plan, making ×plan, other ×plan, days ago)
DEMO_ORDERS = [
    ("ST-0101", 30, 5.30, 0.98, 1.06, 1.10, 1.00, 40),
    ("ST-0104", 120, 5.60, 0.99, 1.10, 1.20, 1.20, 25),   # over plan: loss-making
    ("ST-0102", 45, 9.95, 0.97, 0.98, 0.95, 1.00, 55),
]


class GarmentOrderPnlDemo(models.Model):
    _inherit = "garment.order.pnl"

    @api.model
    def _load_demo(self):
        """Closed demo orders with real source documents: a posted customer invoice, material issued
        from stock, sewing sent out on job work (billed), and other costs typed on the P&L. Then a P&L
        for every running order of the merch demo."""
        Order = self.env["garment.order"].sudo()
        today = fields.Date.context_today(self)
        vendor = self.env["res.partner"].sudo().search([("is_jobwork_vendor", "=", True)], limit=1) or \
            self.env["res.partner"].sudo().create({"name": "Kavya Stitch Works", "is_jobwork_vendor": True})
        issue_product = self.env["product.product"].sudo().create({
            "name": "Fabric and trims issued (demo)", "type": "consu", "standard_price": 1.0})
        stock = self.env["stock.warehouse"].sudo().search([("company_id", "=", self.env.company.id)],
                                                          limit=1).lot_stock_id
        for code, qty, price, ship, f_mat, f_make, f_other, ago in DEMO_ORDERS:
            style = self.env["garment.style"].sudo().search([("code", "=", code)], limit=1)
            if not style or not style.approved_for_production or not stock:
                continue
            order = Order.create({
                "style_id": style.id, "buyer_id": style.buyer_id.id, "price_unit": price,
                "date_order": today - timedelta(days=ago + 60),
                "ex_factory_date": today - timedelta(days=ago),
            })
            for line in order.line_ids:
                line.qty_ordered = qty
            order.action_confirm()
            for line in order.line_ids:
                order._garment_add_progress("shipped", line.colour_id, line.size_id,
                                            int(round(qty * ship)), ref="Demo shipment")
            order.message_post(body="Closed short at the end of shipping (demo).")
            order.state = "closed"
            self._demo_costs(order, f_mat, f_make, f_other, vendor, issue_product, stock, ago)
        # closed merch demo orders without an invoice get theirs too (came in under plan)
        for order in Order.search([("state", "=", "closed")]):
            if not self.env["account.move.line"].sudo().search_count([("garment_order_id", "=", order.id)]):
                self._demo_costs(order, 0.75, 0.85, 0.85, vendor, issue_product, stock, 30)
        Order.search([("state", "not in", ("draft", "cancel"))])._garment_pnl()
        return True

    @api.model
    def _demo_costs(self, order, f_mat, f_make, f_other, vendor, issue_product, stock, ago):
        today = fields.Date.context_today(self)
        style = order.style_id
        price = order.price_unit
        production = issue_product.property_stock_production
        shipped = order.qty_shipped
        invoice = self.env["account.move"].sudo().create({
            "move_type": "out_invoice", "partner_id": order.buyer_id.id,
            "invoice_date": order.ex_factory_date,
            "invoice_line_ids": [Command.create({
                "name": "%s · %s" % (order.name, style.name), "quantity": shipped,
                "price_unit": price, "garment_order_id": order.id, "tax_ids": [Command.clear()]})],
        })
        invoice.action_post()
        move = self.env["stock.move"].sudo().create({
            "name": "Material issued to %s" % order.name, "product_id": issue_product.id,
            "product_uom_qty": round(shipped * order.planned_material_pc * f_mat, 2),
            "product_uom": issue_product.uom_id.id, "location_id": stock.id,
            "location_dest_id": production.id, "garment_pnl_order_id": order.id,
        })
        move._action_confirm()
        move.quantity = move.product_uom_qty
        move.picked = True
        move._action_done()
        jw = self.env["garment.jobwork.order"].sudo().create({
            "vendor_id": vendor.id, "process": "sewing", "qty_sent": shipped,
            "rate": round(order.planned_making_pc * f_make, 2), "production_order_id": order.id,
            "date_issue": today - timedelta(days=ago + 20), "date_expected": today - timedelta(days=ago + 5),
        })
        jw.action_send()
        jw._garment_receive(shipped)
        jw.action_bill()
        pnl = order._garment_pnl(refresh=False)
        pnl.cost_line_ids = [Command.create({
            "date": order.ex_factory_date, "name": "Testing, courier and port charges",
            "amount": round(shipped * order.planned_other_pc * f_other, 2)})]
