from odoo import api, fields, models


class GarmentSizeRange(models.Model):
    _name = "garment.size.range"
    _description = "Garment Size Range"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    size_ids = fields.One2many("garment.size", "range_id", string="Sizes", copy=True)
    size_count = fields.Integer(compute="_compute_size_count")
    size_names = fields.Char(string="Sizes in Order", compute="_compute_size_count")
    active = fields.Boolean(default=True)

    @api.depends("size_ids", "size_ids.name", "size_ids.sequence")
    def _compute_size_count(self):
        for size_range in self:
            sizes = size_range.size_ids.sorted(lambda s: (s.sequence, s.id))
            size_range.size_count = len(sizes)
            size_range.size_names = " · ".join(sizes.mapped("name"))


class GarmentSize(models.Model):
    _name = "garment.size"
    _description = "Garment Size"
    _order = "range_id, sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    range_id = fields.Many2one("garment.size.range", string="Size Range", required=True,
                               ondelete="cascade", index=True)

    _sql_constraints = [
        ("name_range_unique", "unique(range_id, name)", "A size can appear only once in a size range."),
    ]
