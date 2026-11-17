import base64
import csv
import io
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

COLUMNS = ("name", "ratio", "length_m", "width_cm", "efficiency_pct")


class GarmentMarkerImport(models.TransientModel):
    """Import markers exported from the CAD system as CSV.

    Columns: ``name, ratio, length_m, width_cm, efficiency_pct``. ``ratio`` lists size:ratio pairs separated by
    spaces or semicolons, e.g. ``15:1 17:1`` or ``S:1;M:2;L:2``. A marker with the same name on the style is
    updated, so importing twice does not duplicate."""

    _name = "garment.marker.import"
    _description = "Import Markers"

    style_id = fields.Many2one("garment.style", required=True)
    colour_id = fields.Many2one("garment.colour", string="Colourway")
    fabric_id = fields.Many2one("product.product", string="Fabric")
    file = fields.Binary(string="CSV File", required=True)
    filename = fields.Char()
    builder_id = fields.Many2one("garment.cut.plan.builder")

    @api.model
    def _parse_ratio(self, text, style):
        sizes = {s.name.strip().lower(): s for s in style.size_range_id.size_ids}
        result = []
        for token in re.split(r"[;\s]+", (text or "").strip()):
            if not token:
                continue
            if ":" not in token:
                raise UserError(_("Ratio %s must look like SIZE:RATIO.", token))
            size_name, ratio = token.rsplit(":", 1)
            size = sizes.get(size_name.strip().lower())
            if not size:
                raise UserError(_("Size %(size)s is not in the size range of %(style)s.",
                                  size=size_name, style=style.display_name))
            if not ratio.strip().isdigit() or int(ratio) <= 0:
                raise UserError(_("Ratio of size %s must be a whole number above zero.", size_name))
            result.append((size, int(ratio)))
        if not result:
            raise UserError(_("A marker needs at least one size ratio."))
        return result

    def _import_rows(self, rows):
        Marker = self.env["garment.marker"]
        markers = Marker
        for row in rows:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("name"):
                continue
            try:
                length = float(row.get("length_m") or 0)
                width = float(row.get("width_cm") or 0)
                efficiency = float(row.get("efficiency_pct") or 0)
            except ValueError as exc:
                raise UserError(_("Marker %s has a number that cannot be read.", row["name"])) from exc
            ratio = self._parse_ratio(row.get("ratio"), self.style_id)
            vals = {
                "name": row["name"], "style_id": self.style_id.id, "colour_id": self.colour_id.id,
                "fabric_id": self.fabric_id.id, "length_m": length, "width_cm": width, "efficiency_pct": efficiency,
                "line_ids": [(5, 0, 0)] + [(0, 0, {"size_id": s.id, "ratio": r}) for s, r in ratio],
            }
            marker = Marker.search([("style_id", "=", self.style_id.id), ("name", "=", row["name"])], limit=1)
            if marker:
                marker.write(vals)
            else:
                marker = Marker.create(vals)
            markers |= marker
        return markers

    def action_import(self):
        self.ensure_one()
        data = base64.b64decode(self.file or b"")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or not {"name", "ratio", "length_m"} <= {
                (f or "").strip().lower() for f in reader.fieldnames}:
            raise UserError(_("The CSV needs the columns %s.", ", ".join(COLUMNS)))
        markers = self._import_rows(list(reader))
        if self.builder_id:
            return self.builder_id.action_repropose()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_cutting.action_garment_marker")
        action["domain"] = [("id", "in", markers.ids)]
        return action
