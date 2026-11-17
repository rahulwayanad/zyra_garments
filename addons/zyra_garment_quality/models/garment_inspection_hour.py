from odoo import api, fields, models



class GarmentInspectionHour(models.Model):
    _name = "garment.inspection.hour"
    _description = "Pieces and defects checked in one hour"
    _order = "hour_start desc, id desc"

    inspection_id = fields.Many2one("garment.inspection", required=True, ondelete="cascade", index=True)
    hour_start = fields.Datetime(required=True, index=True)
    pieces = fields.Integer()
    defects = fields.Integer()
    kind = fields.Selection(related="inspection_id.kind", store=True)
    line_id = fields.Many2one(related="inspection_id.line_id", store=True, index=True)
    company_id = fields.Many2one(related="inspection_id.company_id", store=True, index=True)

    _sql_constraints = [
        ("hour_unique", "unique(inspection_id, hour_start)", "One count per inspection and hour."),
    ]

    @api.model
    def _garment_add(self, inspection, pieces, defects, when=None):
        hour = self.env["garment.inspection"]._garment_hour_start(when)
        bucket = self.search([("inspection_id", "=", inspection.id), ("hour_start", "=", hour)], limit=1)
        if bucket:
            bucket.write({"pieces": bucket.pieces + pieces, "defects": bucket.defects + defects})
        else:
            bucket = self.create({"inspection_id": inspection.id, "hour_start": hour,
                                  "pieces": pieces, "defects": defects})
        return bucket
