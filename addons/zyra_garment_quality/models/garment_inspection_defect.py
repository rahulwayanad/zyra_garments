from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .garment_inspection import POSITIONS

SEVERITIES = [("critical", "Critical"), ("major", "Major"), ("minor", "Minor")]


class GarmentInspectionDefect(models.Model):
    _name = "garment.inspection.defect"
    _description = "Defect found in an inspection"
    _order = "date desc, id desc"

    inspection_id = fields.Many2one("garment.inspection", required=True, ondelete="cascade", index=True)
    defect_id = fields.Many2one("garment.defect", string="Defect", required=True, index=True)
    severity = fields.Selection(SEVERITIES, string="Class", compute="_compute_severity", store=True,
                                readonly=False, required=True, precompute=True)
    position = fields.Selection(POSITIONS, string="Where")
    qty = fields.Integer(string="Found", default=1, required=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    kind = fields.Selection(related="inspection_id.kind", store=True)
    line_id = fields.Many2one(related="inspection_id.line_id", store=True, index=True)
    order_id = fields.Many2one(related="inspection_id.order_id", store=True)
    style_id = fields.Many2one(related="inspection_id.style_id", store=True)
    company_id = fields.Many2one(related="inspection_id.company_id", store=True, index=True)

    @api.depends("defect_id")
    def _compute_severity(self):
        for line in self:
            line.severity = line.defect_id.severity or line.severity or "minor"

    @api.constrains("qty")
    def _check_qty(self):
        for line in self:
            if line.qty < 1:
                raise ValidationError(self.env._("A defect line counts at least one defect."))

    def _garment_title(self):
        self.ensure_one()
        where = dict(POSITIONS).get(self.position)
        name = self.defect_id.endline_label or self.defect_id.name
        return "%s on %s" % (name, where.lower()) if where else name

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._garment_check_capa()
        return lines

    def _garment_check_capa(self):
        """CAPA trigger: the same defect at the same place on the same line recorded ``threshold`` times
        within ``window`` days raises one corrective action (an open one is updated instead)."""
        Capa = self.env["garment.capa"].sudo()
        seen = set()
        for line in self.filtered(lambda l: l.line_id and l.defect_id):
            key = (line.defect_id.id, line.position or False, line.line_id.id, line.company_id.id)
            if key in seen:
                continue
            seen.add(key)
            company = line.company_id
            since = fields.Datetime.now() - timedelta(days=company.garment_capa_window_days)
            domain = [("defect_id", "=", key[0]), ("position", "=", key[1]), ("line_id", "=", key[2]),
                      ("company_id", "=", key[3])]
            open_capa = Capa.search(domain[:2] + [("line_ids", "in", key[2]), ("company_id", "=", key[3]),
                                                  ("state", "in", ("open", "in_progress"))], limit=1)
            if open_capa:
                first = fields.Datetime.to_datetime(open_capa.first_seen)
                recent = self.sudo().search(domain + [("date", ">=", first)])
                open_capa.write({
                    "occurrences": sum(recent.mapped("qty")),
                    "inspection_ids": [(4, i) for i in recent.mapped("inspection_id").ids],
                })
                continue
            recent = self.sudo().search(domain + [("date", ">=", since)])
            total = sum(recent.mapped("qty"))
            if total < company.garment_capa_threshold:
                continue
            Capa._garment_raise_from_defects(recent, total, company.garment_capa_window_days)
