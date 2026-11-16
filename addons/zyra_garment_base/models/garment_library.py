import csv
import io
import re

from odoo import Command, api, models
from odoo.tools import file_open

MODULE = "zyra_garment_base"
LIBRARY_PATH = "zyra_garment_base/data/library/"

# key -> (label, CSV column value)
SIZE_PRESETS = {
    "s_xl": "S-XL",
    "xs_xxl": "XS-XXL",
    "kids_2_14": "Kids 2-14",
}


def _xmlid_part(value):
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


class GarmentLibrary(models.AbstractModel):
    """Loads the shipped libraries (points of measure, defects, size presets).

    Every loader is idempotent: a record is matched by its code (or by its xml id for
    size ranges) and only created when missing. Created records get an xml id in this
    module (``zyra_garment_base.pom_<code>``, ``defect_<code>``, ``size_range_<preset>``,
    ``size_<preset>_<size>``) so other modules' demo data can refer to them.
    """

    _name = "garment.library"
    _description = "Garment Library Loader"

    @api.model
    def _read_library_csv(self, filename):
        with file_open(LIBRARY_PATH + filename, "rb") as handle:
            text = handle.read().decode("utf-8")
        return list(csv.DictReader(io.StringIO(text)))

    @api.model
    def _register_xmlid(self, record, name):
        self.env["ir.model.data"].sudo().create({
            "module": MODULE,
            "name": name,
            "model": record._name,
            "res_id": record.id,
            "noupdate": True,
        })

    @api.model
    def _xmlid_record(self, name):
        return self.env.ref(f"{MODULE}.{name}", raise_if_not_found=False)

    @api.model
    def _load_coded_library(self, model_name, filename, prefix, fields_map):
        Model = self.env[model_name].with_context(active_test=False).sudo()
        existing = set(Model.search([]).mapped("code"))
        created = Model.browse()
        for sequence, row in enumerate(self._read_library_csv(filename), start=1):
            code = row["code"].strip()
            if code in existing:
                continue
            vals = {"sequence": sequence * 10}
            for column, (field_name, cast) in fields_map.items():
                vals[field_name] = cast(row[column].strip())
            record = Model.create(vals)
            existing.add(code)
            created |= record
            if not self._xmlid_record(f"{prefix}_{_xmlid_part(code)}"):
                self._register_xmlid(record, f"{prefix}_{_xmlid_part(code)}")
        return created

    @api.model
    def _load_pom_library(self):
        """Create the shipped points of measure that do not exist yet."""
        return self._load_coded_library("garment.pom", "garment_pom_library.csv", "pom", {
            "code": ("code", str),
            "name": ("name", str),
            "used_on": ("garment_category", str),
            "how_to_measure": ("how_to_measure", str),
            "tolerance_cm": ("default_tolerance", float),
        })

    @api.model
    def _load_defect_library(self):
        """Create the shipped defects that do not exist yet."""
        return self._load_coded_library("garment.defect", "garment_defect_library.csv", "defect", {
            "code": ("code", str),
            "name": ("name", str),
            "area": ("area", str),
            "severity": ("severity", str),
            "department": ("department", str),
        })

    @api.model
    def _load_size_preset(self, preset):
        """Return the size range of ``preset`` (a SIZE_PRESETS key), creating it once."""
        if preset not in SIZE_PRESETS:
            raise ValueError(f"Unknown size preset {preset!r}")
        xmlid = f"size_range_{preset}"
        size_range = self._xmlid_record(xmlid)
        if size_range:
            return size_range
        Range = self.env["garment.size.range"].sudo()
        rows = [r for r in self._read_library_csv("garment_size_presets.csv") if r["preset"] == preset]
        label = SIZE_PRESETS[preset]
        size_range = Range.with_context(active_test=False).search([("name", "=", label)], limit=1)
        if not size_range:
            size_range = Range.create({
                "name": label,
                "sequence": list(SIZE_PRESETS).index(preset) + 1,
                "size_ids": [Command.create({"name": r["size"], "sequence": int(r["sequence"])}) for r in rows],
            })
            for size in size_range.size_ids:
                self._register_xmlid(size, f"size_{preset}_{_xmlid_part(size.name)}")
        self._register_xmlid(size_range, xmlid)
        return size_range

    @api.model
    def _load_demo_libraries(self):
        """Demo data hook: load every library and every size preset."""
        self._load_pom_library()
        self._load_defect_library()
        for preset in SIZE_PRESETS:
            self._load_size_preset(preset)
        return True

    @api.model
    def _demo_receive_rolls(self, quantities):
        """Demo data hook: put demo rolls in stock. ``quantities`` maps lot xml id -> metres."""
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        if not warehouse:
            return False
        Quant = self.env["stock.quant"].sudo()
        for xmlid, qty in quantities.items():
            lot = self.env.ref(xmlid, raise_if_not_found=False)
            if lot and not lot.quant_ids:
                Quant._update_available_quantity(lot.product_id, warehouse.lot_stock_id, qty, lot_id=lot)
        return True
