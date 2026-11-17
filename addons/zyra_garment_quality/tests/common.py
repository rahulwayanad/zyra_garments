from datetime import timedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user


class QualityCase(TransactionCase):
    """One confirmed production order (1 colour × 2 sizes, 1,000 pieces) on its own sewing line."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.company
        cls.company.write({"garment_aql_major": 2.5, "garment_aql_minor": 4.0, "garment_dhu_limit": 5.0,
                           "garment_capa_threshold": 10, "garment_capa_window_days": 3})
        cls.today = fields.Date.context_today(env["garment.order"])
        size_range = env["garment.size.range"].create({
            "name": "QA S-M",
            "size_ids": [Command.create({"name": n, "sequence": i}) for i, n in enumerate(["S", "M"])],
        })
        cls.s, cls.m = size_range.size_ids.sorted("sequence")
        cls.colour = env["garment.colour"].create({"name": "QA Teal", "code": "QAT", "hex": "#118899"})
        cls.buyer = env["res.partner"].create({"name": "QA Buyer", "is_garment_buyer": True})
        cls.style = env["garment.style"].create({
            "name": "QA Tee", "code": "QA-0001", "buyer_id": cls.buyer.id,
            "size_range_id": size_range.id, "colour_ids": [Command.set(cls.colour.ids)],
        })
        cls.line = env["mrp.workcenter"].create({"name": "QA Line 9 · Knit", "code": "QA9"})
        cls.order = cls._make_order(cls.line)
        Defect = env["garment.defect"]
        cls.d_major = Defect.create({"code": "QAMJ", "name": "QA puckering", "area": "stitching",
                                     "severity": "major", "department": "sewing"})
        cls.d_minor = Defect.create({"code": "QAMN", "name": "QA loose thread", "area": "finishing",
                                     "severity": "minor", "department": "sewing"})
        cls.d_critical = Defect.create({"code": "QACR", "name": "QA hole", "area": "fabric",
                                        "severity": "critical", "department": "sewing"})
        cls.quality_user = new_test_user(env, "qa_inspector", groups="zyra_garment_base.group_garment_quality")
        cls.manager = new_test_user(env, "qa_manager", groups="zyra_garment_base.group_garment_factory_manager")

    @classmethod
    def _make_order(cls, line):
        order = cls.env["garment.order"].create({
            "style_id": cls.style.id,
            "buyer_id": cls.buyer.id,
            "ex_factory_date": cls.today + timedelta(days=20),
            "date_order": cls.today - timedelta(days=40),
            "price_unit": 5.0,
            "sewing_line_id": line.id,
        })
        for cell in order.line_ids:
            cell.qty_ordered = 500
        order.state = "confirmed"  # the style approval gate belongs to merch's own tests
        return order

    def inspect(self, kind="final", pieces=125, defects=(), lot=1633, order=None, complete=False, **vals):
        """``defects``: iterable of (defect, qty[, position])."""
        lines = [Command.create({"defect_id": d[0].id, "qty": d[1], "position": d[2] if len(d) > 2 else False})
                 for d in defects]
        insp = self.env["garment.inspection"].create(dict({
            "kind": kind, "order_id": (order or self.order).id, "pieces_checked": pieces,
            "lot_size": lot if kind == "final" else 0, "defect_line_ids": lines,
        }, **vals))
        if complete:
            insp.action_complete()
        return insp
