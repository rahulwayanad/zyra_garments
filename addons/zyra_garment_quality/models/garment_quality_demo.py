"""Demo loader for quality: inspections over the last week on the merch demo orders, a failed final on
the late order (shipment blocked), today's end-line tablet session on Line 2 and the CAPA that the repeated
puckering raised by itself. Dates are relative to the install moment."""
from datetime import timedelta

from odoo import api, fields, models

B = "zyra_garment_base."
M = "zyra_garment_merch."
Q = "zyra_garment_quality."

TABLET_LABELS = [
    ("W01", "Broken stitch"), ("W02", "Skip stitch"), ("W04", "Puckering"), ("W10", "Uneven hem"),
    ("D05", "Stain"), ("W07", "Open seam"), ("S01", "Shade variation"), ("M01", "Measurement out"),
]


class GarmentQualityDemo(models.AbstractModel):
    _name = "garment.quality.demo"
    _description = "Quality demo loader"

    def _ref(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _xmlid(self, record, name):
        self.env["ir.model.data"]._update_xmlids([{"xml_id": Q + name, "record": record, "noupdate": True}])

    def _defect(self, code):
        return self.env["garment.defect"].search([("code", "=", code)], limit=1)

    def _inspect(self, order, kind, when, pieces, defects, complete=True, lot=None, xmlid=None):
        """``defects``: list of (code, position or False, qty)."""
        inspector = self._ref(B + "user_priya") or self.env.user
        lines = []
        for code, position, qty in defects:
            defect = self._defect(code)
            if defect:
                lines.append((0, 0, {"defect_id": defect.id, "position": position, "qty": qty, "date": when}))
        vals = {
            "kind": kind, "order_id": order.id, "date": when, "pieces_checked": pieces,
            "inspector_id": inspector.id, "defect_line_ids": lines,
        }
        if kind == "final":
            vals["lot_size"] = lot or order.qty_packed or order.qty_ordered
        insp = self.env["garment.inspection"].create(vals)
        if complete:
            insp.action_complete()
        if xmlid:
            self._xmlid(insp, xmlid)
        return insp

    @api.model
    def _load_demo(self):
        if self._ref(Q + "inspection_final_tee_failed"):
            return True
        tee = self._ref(M + "order_tee_late")
        jean = self._ref(M + "order_jean_late")
        polo = self._ref(M + "order_polo_running")
        chino = self._ref(M + "order_chino_running")
        polo_done = self._ref(M + "order_polo_shipped")
        if not (tee and jean and polo and chino and polo_done):
            return True  # merchandising demo not loaded
        for seq, (code, label) in enumerate(TABLET_LABELS):
            defect = self._defect(code)
            if defect:
                defect.write({"endline_button": True, "endline_label": label, "endline_sequence": seq})

        now = fields.Datetime.now()
        ago = lambda days, hours=0: now - timedelta(days=days, hours=hours)  # noqa: E731

        # Older history: the shipped polo passed its final last month.
        self._inspect(polo_done, "final", ago(32), 80, [("W01", "side_seams", 1), ("D03", False, 2)], lot=600)

        # Jean (Line 4): inline, end-line, failed final (majors above the accept number).
        self._inspect(jean, "inline", ago(5, 3), 20, [("W03", "side_seams", 2), ("W10", "hem", 1)])
        self._inspect(jean, "endline", ago(3, 2), 32, [("W01", "side_seams", 2), ("D03", False, 3)])
        self._inspect(jean, "final", ago(2, 4), 80, [("W01", "side_seams", 3), ("M01", False, 4),
                                                     ("D03", False, 3)], xmlid="inspection_final_jean_failed")

        # Polo (Line 1): inline, end-line and a passed final on the first packed lot.
        self._inspect(polo, "inline", ago(5, 1), 50, [("W02", "collar", 2), ("W05", "front_left", 5)])
        self._inspect(polo, "endline", ago(2, 5), 20, [("W03", "back", 1)])
        self._inspect(polo, "final", ago(1, 6), 50, [("W08", "hem", 2), ("D03", False, 3)],
                      xmlid="inspection_final_polo_passed")

        # Chino (Line 4): early checks.
        self._inspect(chino, "inline", ago(1, 3), 20, [("W03", "waistband", 3)])
        self._inspect(chino, "endline", ago(0, 1), 20, [])

        # Tee, the late order (Line 2): puckering on the left sleeve keeps coming back.
        self._inspect(tee, "inline", ago(3, 5), 32, [("W04", "left_sleeve", 2), ("W02", "collar", 2),
                                                     ("W10", "hem", 5)])
        self._inspect(tee, "endline", ago(2, 3), 60, [("W04", "left_sleeve", 5), ("W01", "side_seams", 1)])
        self._inspect(tee, "endline", ago(1, 2), 64, [("W04", "left_sleeve", 5), ("W02", "collar", 2)])
        failed = self._inspect(tee, "final", ago(1, 1), 200, [
            ("W01", "side_seams", 5), ("W09", "side_seams", 4), ("W14", "front_left", 3),
            ("W10", "hem", 5), ("D03", False, 4),
        ], xmlid="inspection_final_tee_failed")
        reinspect = failed.action_reinspect()
        self._xmlid(self.env["garment.inspection"].browse(reinspect["res_id"]), "inspection_final_tee_reinspection")

        self._load_tablet_session(tee, now)
        self._load_capas(tee, failed)
        return True

    def _load_tablet_session(self, order, now):
        """Today's end-line session on Line 2: 310 pieces, 12 defects; this hour 46 pieces, 2 defects."""
        Insp = self.env["garment.inspection"]
        today_start = Insp._garment_today_start()
        start = max(today_start + timedelta(minutes=1), now - timedelta(hours=5))
        session = Insp.create({
            "kind": "endline", "order_id": order.id, "date": start, "pieces_checked": 310,
            "inspector_id": (self._ref(B + "user_priya") or self.env.user).id,
        })
        self._xmlid(session, "inspection_endline_tee_today")
        Hour = self.env["garment.inspection.hour"]
        hour = Insp._garment_hour_start(now)
        Hour.create({"inspection_id": session.id, "hour_start": hour, "pieces": 46, "defects": 2})
        earlier = [(1, 70, 3), (2, 66, 2), (3, 64, 3), (4, 64, 2)]
        for back, pieces, defects in earlier:
            Hour.create({"inspection_id": session.id, "hour_start": hour - timedelta(hours=back),
                         "pieces": pieces, "defects": defects})
        found = [
            ("W04", "left_sleeve", 0), ("W01", "side_seams", 0),
            ("W04", "left_sleeve", 1), ("W02", "collar", 1), ("W10", "hem", 1),
            ("W04", "left_sleeve", 2), ("D05", "front_right", 2),
            ("W04", "left_sleeve", 3), ("W01", "side_seams", 3), ("W10", "hem", 3),
            ("W02", "collar", 4), ("M01", "back", 4),
        ]
        for code, position, back in found:
            when = max(start, now - timedelta(hours=back, minutes=1)) if back else now
            self.env["garment.inspection.defect"].create({
                "inspection_id": session.id, "defect_id": self._defect(code).id, "position": position,
                "qty": 1, "date": when})

    def _load_capas(self, order, failed):
        today = fields.Date.context_today(self)
        Capa = self.env["garment.capa"]
        auto = Capa.search([("auto_raised", "=", True), ("order_id", "=", order.id)], limit=1)
        arjun = self._ref(B + "user_arjun") or self.env.user
        priya = self._ref(B + "user_priya") or self.env.user
        if auto:
            auto.write({
                "title": "Puckering on left sleeve attach",
                "state": "in_progress",
                "root_cause": "Feed dog pressure too high on the 4-thread overlock of the sleeve attach station",
                "action": "Reset pressure, retrain the operator, check every 2 hours",
                "owner_id": arjun.id,
                "due_date": today + timedelta(days=3),
                "verification": "DHU below 2% for 3 days",
            })
            self._xmlid(auto, "capa_tee_puckering")
        capa = Capa.create({
            "title": "Broken stitch and seam twist at side seams",
            "source": "final",
            "defect_id": self._defect("W09").id,
            "position": "side_seams",
            "line_ids": [(6, 0, failed.line_id.ids)],
            "style_id": order.style_id.id,
            "order_id": order.id,
            "inspection_ids": [(6, 0, failed.ids)],
            "first_seen": today - timedelta(days=1),
            "occurrences": 9,
            "occurrence_days": 1,
            "owner_id": priya.id,
            "due_date": today + timedelta(days=5),
            "verification": "Re-inspection of the lot passes",
        })
        self._xmlid(capa, "capa_tee_side_seams")
