from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GarmentMarker(models.Model):
    """A marker: the pattern layout of a size ratio on one fabric width. Entered from the CAD system,
    never drawn here. One ply under the marker gives ``pieces_per_ply`` garments."""

    _name = "garment.marker"
    _description = "Cutting Marker"
    _order = "style_id, sequence, name, id"
    _check_company_auto = True

    name = fields.Char(required=True, help="Marker name from the CAD system, e.g. M-15/17.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    style_id = fields.Many2one("garment.style", required=True, ondelete="cascade", index=True,
                               check_company=True)
    size_range_id = fields.Many2one(related="style_id.size_range_id")
    colour_id = fields.Many2one("garment.colour", string="Colourway",
                                help="Leave empty when the marker is used for every colourway of the style.")
    fabric_id = fields.Many2one("product.product", string="Fabric", check_company=True)
    line_ids = fields.One2many("garment.marker.line", "marker_id", string="Size Ratio", copy=True)
    ratio_text = fields.Char(string="Size Ratio", compute="_compute_ratio", store=True)
    ratio_short = fields.Char(string="Ratio", compute="_compute_ratio", store=True)
    pieces_per_ply = fields.Integer(compute="_compute_ratio", store=True,
                                    help="Garments cut from one ply = sum of the size ratio.")
    length_m = fields.Float(string="Marker Length (m)", digits=(16, 3), required=True)
    width_cm = fields.Float(string="Width (cm)")
    efficiency_pct = fields.Float(string="Efficiency %", digits=(16, 2))
    note = fields.Char()

    _sql_constraints = [
        ("length_positive", "CHECK(length_m > 0)", "A marker needs a length above zero."),
        ("efficiency_range", "CHECK(efficiency_pct >= 0 AND efficiency_pct <= 100)",
         "Marker efficiency is a percentage between 0 and 100."),
    ]

    @api.depends("line_ids.ratio", "line_ids.size_id", "line_ids.size_id.name", "line_ids.size_id.sequence")
    def _compute_ratio(self):
        for marker in self:
            lines = marker.line_ids.filtered(lambda l: l.size_id and l.ratio > 0).sorted(
                lambda l: (l.size_id.sequence, l.size_id.id))
            marker.pieces_per_ply = sum(lines.mapped("ratio"))
            marker.ratio_text = " + ".join("%s × %s" % (l.size_id.name, l.ratio) for l in lines)
            if len(lines) == 1:
                marker.ratio_short = "%s:%s" % (lines.size_id.name, lines.ratio)
            else:
                marker.ratio_short = ":".join(str(r) for r in lines.mapped("ratio"))

    @api.depends("name", "ratio_short")
    def _compute_display_name(self):
        for marker in self:
            marker.display_name = "%s (%s)" % (marker.name, marker.ratio_short) if marker.ratio_short \
                else (marker.name or "")

    @api.constrains("line_ids", "style_id")
    def _check_sizes(self):
        for marker in self:
            sizes = marker.line_ids.mapped("size_id")
            if len(sizes) != len(marker.line_ids):
                raise ValidationError(_("Marker %s lists a size twice.", marker.name))
            rng = marker.style_id.size_range_id
            if rng and sizes - rng.size_ids:
                raise ValidationError(_("Marker %(marker)s uses sizes outside the size range %(range)s.",
                                        marker=marker.name, range=rng.name))

    def _ratio_by_size(self):
        """{size_id: ratio} of this marker."""
        self.ensure_one()
        return {l.size_id.id: l.ratio for l in self.line_ids if l.size_id and l.ratio > 0}


class GarmentMarkerLine(models.Model):
    _name = "garment.marker.line"
    _description = "Marker Size Ratio"
    _order = "marker_id, size_sequence, id"

    marker_id = fields.Many2one("garment.marker", required=True, ondelete="cascade", index=True)
    size_id = fields.Many2one("garment.size", required=True)
    size_sequence = fields.Integer(related="size_id.sequence", store=True)
    ratio = fields.Integer(default=1, required=True, help="Garments of this size in one ply of the marker.")

    _sql_constraints = [
        ("ratio_positive", "CHECK(ratio > 0)", "A size ratio is a whole number above zero."),
    ]
