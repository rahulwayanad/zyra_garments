from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.zyra_garment_base.models.garment_operation import OPERATION_SECTIONS

MATERIAL_KINDS = [("fabric", "Fabric"), ("trim", "Trim"), ("packing", "Packing")]

STITCH_CLASSES = [
    ("101", "101 · Single-thread chainstitch"),
    ("301", "301 · Lockstitch"),
    ("401", "401 · Two-thread chainstitch"),
    ("406", "406 · Two-needle coverstitch"),
    ("504", "504 · Three-thread overlock"),
    ("514", "514 · Four-thread overlock"),
    ("516", "516 · Safety stitch"),
    ("602", "602 · Top-and-bottom coverstitch"),
    ("605", "605 · Three-needle coverstitch"),
    ("bartack", "Bartack"),
    ("buttonhole", "Buttonhole"),
]

SEAM_TYPES = [
    ("superimposed", "Superimposed"),
    ("lapped", "Lapped"),
    ("bound", "Bound"),
    ("flat", "Flat"),
    ("edge_finish", "Edge finish / hem"),
    ("ornamental", "Ornamental"),
]


class TechpackLineMixin(models.AbstractModel):
    """Lines of an approved or superseded tech pack cannot be added, changed or removed."""
    _name = "zyra.techpack.line.mixin"
    _description = "Tech Pack Line (lock rule)"

    def _check_techpack_open(self, techpacks):
        if self.env.context.get("techpack_unlock"):
            return
        locked = techpacks.filtered(lambda t: t.state in ("approved", "superseded"))
        if locked:
            raise UserError(_("Tech pack %s is approved and cannot be changed. Make a new version instead.",
                              ", ".join(locked.mapped("name"))))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._check_techpack_open(records.techpack_id)
        return records

    def write(self, vals):
        self._check_techpack_open(self.techpack_id)
        res = super().write(vals)
        if "techpack_id" in vals:
            self._check_techpack_open(self.techpack_id)
        return res

    def unlink(self):
        self._check_techpack_open(self.techpack_id)
        return super().unlink()


class ZyraTechpackBomLine(models.Model):
    _name = "zyra.techpack.bom.line"
    _inherit = ["zyra.techpack.line.mixin"]
    _description = "Tech Pack Material"
    _order = "techpack_id, sequence, id"

    techpack_id = fields.Many2one("zyra.techpack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", string="Material", required=True,
                                 domain="[('type', '=', 'consu')]")
    material_kind = fields.Selection(MATERIAL_KINDS, string="Kind", required=True, default="fabric")
    placement = fields.Char()
    colour_id = fields.Many2one("garment.colour", string="Colourway",
                                help="Empty = used in every colourway.")
    size_id = fields.Many2one("garment.size", string="Size", help="Empty = used in every size.")
    consumption = fields.Float(digits=(16, 4), required=True, default=1.0, help="Per piece, in the unit below.")
    uom_id = fields.Many2one("uom.uom", string="Unit", required=True,
                             compute="_compute_uom_id", store=True, readonly=False, precompute=True)
    wastage_pct = fields.Float(string="Wastage %", digits=(16, 2), help="Percent: 3.0 = 3 %.")
    # Float, not Monetary: Monetary rounds to the currency (2 decimals) and trims cost a fraction of a cent.
    price_unit = fields.Float(string="Price", digits="Product Price",
                                 compute="_compute_price_unit", store=True, readonly=False, precompute=True)
    currency_id = fields.Many2one(related="techpack_id.currency_id")
    qty_with_wastage = fields.Float(digits=(16, 4), compute="_compute_figures", store=True,
                                    help="Consumption × (1 + wastage %).")
    cost_per_piece = fields.Float(string="Cost / pc", digits=(16, 4),
                                     compute="_compute_figures", store=True)

    _sql_constraints = [
        ("consumption_positive", "CHECK(consumption >= 0)", "Consumption cannot be negative."),
        ("wastage_range", "CHECK(wastage_pct >= 0 AND wastage_pct < 100)", "Wastage must be 0 to 99 %."),
    ]

    @api.depends("product_id")
    def _compute_uom_id(self):
        for line in self:
            if line.product_id and (not line.uom_id or line.uom_id.category_id != line.product_id.uom_id.category_id):
                line.uom_id = line.product_id.uom_id

    @api.depends("product_id")
    def _compute_price_unit(self):
        for line in self:
            if line.product_id and not line.price_unit:
                line.price_unit = line.product_id.standard_price

    @api.depends("consumption", "wastage_pct", "price_unit")
    def _compute_figures(self):
        for line in self:
            line.qty_with_wastage = line.consumption * (1.0 + line.wastage_pct / 100.0)
            line.cost_per_piece = line.qty_with_wastage * line.price_unit

    @api.constrains("uom_id", "product_id")
    def _check_uom(self):
        for line in self:
            if line.uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_("The unit of %(product)s must be in the same category as %(uom)s.",
                                        product=line.product_id.display_name, uom=line.product_id.uom_id.name))

    @api.constrains("colour_id", "size_id", "techpack_id")
    def _check_colour_size(self):
        for line in self:
            style = line.techpack_id.style_id
            if line.colour_id and line.colour_id not in style.colour_ids:
                raise ValidationError(_("Colourway %(colour)s is not a colourway of style %(style)s.",
                                        colour=line.colour_id.name, style=style.code))
            if line.size_id and line.size_id.range_id != style.size_range_id:
                raise ValidationError(_("Size %(size)s is not in the size range of style %(style)s.",
                                        size=line.size_id.name, style=style.code))


class ZyraTechpackMeasurement(models.Model):
    _name = "zyra.techpack.measurement"
    _inherit = ["zyra.techpack.line.mixin"]
    _description = "Tech Pack Measurement Point"
    _order = "techpack_id, sequence, id"

    techpack_id = fields.Many2one("zyra.techpack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    pom_id = fields.Many2one("garment.pom", string="Point of Measure", required=True)
    pom_code = fields.Char(related="pom_id.code", string="Code")
    base_value = fields.Float(string="Base Size Value", digits=(16, 2))
    tol_plus = fields.Float(string="Tol +", digits=(16, 2), compute="_compute_tolerance", store=True,
                            readonly=False, precompute=True)
    tol_minus = fields.Float(string="Tol −", digits=(16, 2), compute="_compute_tolerance", store=True,
                             readonly=False, precompute=True)
    grade_rule = fields.Float(digits=(16, 2), help="Increment per size step from the base size.")

    _sql_constraints = [
        ("pom_unique", "unique(techpack_id, pom_id)", "A point of measure appears only once per tech pack."),
        ("tolerance_positive", "CHECK(tol_plus >= 0 AND tol_minus >= 0)", "Tolerances are given as positive "
                                                                         "numbers."),
    ]

    @api.depends("pom_id")
    def _compute_tolerance(self):
        for line in self:
            if line.pom_id and not line.tol_plus and not line.tol_minus:
                line.tol_plus = line.pom_id.default_tolerance
                line.tol_minus = line.pom_id.default_tolerance


class ZyraTechpackConstruction(models.Model):
    _name = "zyra.techpack.construction"
    _inherit = ["zyra.techpack.line.mixin"]
    _description = "Tech Pack Construction Detail"
    _order = "techpack_id, sequence, id"

    techpack_id = fields.Many2one("zyra.techpack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    area = fields.Char(string="Garment Area", required=True)
    stitch_class = fields.Selection(STITCH_CLASSES)
    spi = fields.Integer(string="SPI", help="Stitches per inch.")
    seam_type = fields.Selection(SEAM_TYPES)
    seam_allowance = fields.Float(digits=(16, 2), help="In the tech pack's measuring unit.")
    note = fields.Char(string="Sewing Note")

    _sql_constraints = [
        ("spi_positive", "CHECK(spi >= 0)", "SPI cannot be negative."),
    ]


class ZyraTechpackOperation(models.Model):
    _name = "zyra.techpack.operation"
    _inherit = ["zyra.techpack.line.mixin"]
    _description = "Tech Pack Operation"
    _order = "techpack_id, sequence, id"

    techpack_id = fields.Many2one("zyra.techpack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    operation_id = fields.Many2one("garment.operation", string="Operation", required=True)
    name = fields.Char(string="Description", compute="_compute_from_operation", store=True, readonly=False,
                       precompute=True)
    section = fields.Selection(OPERATION_SECTIONS, compute="_compute_from_operation", store=True,
                               readonly=False, precompute=True)
    machine_type_id = fields.Many2one("garment.machine.type", string="Machine",
                                      compute="_compute_from_operation", store=True, readonly=False,
                                      precompute=True)
    sam = fields.Float(string="SAM", digits=(16, 3), compute="_compute_from_operation", store=True,
                       readonly=False, precompute=True)

    _sql_constraints = [
        ("sam_positive", "CHECK(sam >= 0)", "SAM cannot be negative."),
    ]

    @api.depends("operation_id")
    def _compute_from_operation(self):
        for line in self:
            op = line.operation_id
            if not op:
                continue
            if not line.name:
                line.name = op.name
            if not line.section:
                line.section = op.section
            if not line.machine_type_id:
                line.machine_type_id = op.machine_type_id
            if not line.sam:
                line.sam = op.default_sam
