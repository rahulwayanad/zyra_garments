from datetime import timedelta

from odoo import api, fields, models

FM_GROUP = "zyra_garment_base.group_garment_factory_manager"


class GarmentShippingDemo(models.AbstractModel):
    _name = "garment.shipping.demo"
    _description = "Packing and shipping demo loader"

    @api.model
    def _load_demo(self):
        """Pack plans, cartons, letters of credit and shipments on the merchandising demo orders
        (screens 67-73, 76). Invented names only. Skips quietly when the merch demo is not there."""
        Order = self.env["garment.order"]
        orders = {o.name: o for o in Order.search([("state", "not in", ("draft", "cancel", "closed"))])}
        today = fields.Date.context_today(self)
        o1, o2, o3, o4 = (orders.get("PO/2026/000%s" % i) for i in (1, 2, 3, 4))
        if not (o1 and o2 and o3 and o4):
            return True

        # ---------------------------------------------------------------- pack plans (screens 67-69)
        def plan_for(order, kind, ppc=0, ratio=None, pack=0, **vals):
            sizes = order.line_ids.mapped("size_id").sorted("sequence")
            lines = []
            if kind != "solid":
                ratio = ratio or [8 if i in (1, 2) else 4 for i in range(len(sizes))]
                lines = [fields.Command.create({"size_id": s.id, "qty": q}) for s, q in zip(sizes, ratio)]
            plan = self.env["garment.pack.plan"].create(dict({
                "order_id": order.id, "pack_kind": kind, "ratio_line_ids": lines, "pieces_per_carton": ppc,
                "length_cm": 60, "width_cm": 40, "height_cm": 30,
                "net_weight_per_piece": 0.22, "empty_carton_weight": 0.95,
            }, **vals))
            plan.action_generate_cartons()
            if pack:
                plan.carton_ids.sorted("number")[:pack].action_pack()
            return plan

        plan_for(o1, "assorted", pack=120)
        plan_for(o2, "solid", ppc=20, pack=40, net_weight_per_piece=0.65, height_cm=35)
        plan_for(o3, "solid", ppc=24, pack=50, net_weight_per_piece=0.28)
        plan_for(o4, "assorted", pack=30, net_weight_per_piece=0.48)

        # ---------------------------------------------------------------- letters of credit (screens 72-73)
        Lc = self.env["garment.lc"]
        lc_expired = Lc.create({
            "name": "LCBF480215", "buyer_id": o4.buyer_id.id, "issuing_bank": "Harbourline Bank, Boston",
            "advising_bank": "Coastal Commerce Bank, Kochi", "amount": 48000.0, "tolerance_pct": 5.0,
            "latest_shipment_date": today - timedelta(days=40), "expiry_date": today - timedelta(days=12),
            "state": "open",
        })
        lc_soon = Lc.create({
            "name": "LCMF30762", "buyer_id": o3.buyer_id.id, "issuing_bank": "Rheinbank Frankfurt",
            "advising_bank": "Coastal Commerce Bank, Kochi", "amount": 40000.0, "tolerance_pct": 5.0,
            "latest_shipment_date": today + timedelta(days=11), "expiry_date": today + timedelta(days=6),
            "state": "open",
        })
        lc_long = Lc.create({
            "name": "LCNW22917", "buyer_id": o1.buyer_id.id, "issuing_bank": "Northgate Trust NY",
            "advising_bank": "Coastal Commerce Bank, Kochi", "amount": 60000.0, "tolerance_pct": 10.0,
            "latest_shipment_date": today + timedelta(days=28), "expiry_date": today + timedelta(days=75),
            "state": "open",
        })

        # ---------------------------------------------------------------- shipments (screens 70-71)
        Shipment = self.env["garment.shipment"]
        incoterm = self.env.ref("account.incoterm_FOB", raise_if_not_found=False)

        def shipment(order, lc, planned, mode="sea", port="Kochi", **vals):
            ship = Shipment.create(dict({
                "buyer_id": order.buyer_id.id, "order_ids": [fields.Command.set(order.ids)],
                "lc_id": lc.id if lc else False, "planned_date": planned, "mode": mode,
                "port_loading": port, "incoterm_id": incoterm.id if incoterm else False,
            }, **vals))
            ship.action_add_packed_cartons()
            return ship

        # Late air shipment under an expired credit, let go by a manager, now paid (screen 71).
        late = shipment(o4, lc_expired, today - timedelta(days=20), mode="air", port="Kochi Intl",
                        port_discharge="Boston Logan", forwarder="Skybridge Cargo", vessel_flight="SB 512",
                        transport_doc_no="176-55102384", actual_date=today - timedelta(days=11))
        late.action_confirm()
        manager = self.env.ref("base.user_admin")
        if not manager.has_group(FM_GROUP):
            manager.sudo().write({"groups_id": [fields.Command.link(self.env.ref(FM_GROUP).id)]})
        late.with_user(manager)._garment_override(
            "Buyer confirmed by e-mail that the credit is being extended; goods released on air freight.")
        late.action_ex_factory()
        late.action_handed_over()
        late.action_on_board()
        late.action_documents_presented()
        late.action_paid()

        # On board, on time, on a healthy credit.
        board = shipment(o3, lc_soon, today - timedelta(days=3), port="Chennai",
                         port_discharge="Hamburg", forwarder="Bluewater Logistics", vessel_flight="MV Coral Dawn",
                         transport_doc_no="BWL-KOC-88142", actual_date=today - timedelta(days=3))
        board.action_confirm()
        board.action_ex_factory()
        board.action_handed_over()
        board.action_on_board()

        # Confirmed and waiting to leave; draft for the next lot.
        confirmed = shipment(o1, lc_long, today + timedelta(days=6), port_discharge="New York")
        confirmed.action_confirm()
        shipment(o2, False, today + timedelta(days=12), port_discharge="Rotterdam")
        return True
