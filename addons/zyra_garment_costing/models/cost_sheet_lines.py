from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MATERIAL_KINDS = [("fabric", "Fabric"), ("trim", "Trim"), ("packing", "Packing")]


class GarmentCostSheetMaterial(models.Model):
    _name = "garment.cost.sheet.material"
    _description = "Cost Sheet Material Line"
    _order = "sheet_id, material_kind, sequence, id"

    sheet_id = fields.Many2one("garment.cost.sheet", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="sheet_id.company_id", store=True)
    currency_id = fields.Many2one(related="sheet_id.currency_id")
    sequence = fields.Integer(default=10)
    material_kind = fields.Selection(MATERIAL_KINDS, string="Kind", required=True, default="fabric")
    method = fields.Selection(
        [("techpack", "Tech Pack"), ("manual", "Manual")], string="Method", required=True, default="manual",
        help="Tech Pack: loaded from the tech pack BoM (replaced on reload). Manual: entered here.",
    )
    product_id = fields.Many2one("product.product", string="Material", required=True)
    colour_id = fields.Many2one("garment.colour", string="Colourway", help="Empty = all colourways.")
    consumption = fields.Float(string="Consumption", digits=(16, 4), help="Per piece, in the unit.")
    uom_id = fields.Many2one(
        "uom.uom", string="Unit", compute="_compute_uom_id", store=True, readonly=False, precompute=True,
    )
    wastage_pct = fields.Float(string="Wastage %", digits=(16, 1), help="Percent: 3.0 means 3 %.")
    price_unit = fields.Float(string="Price", digits=(16, 4), help="Per unit, company currency.")
    share_pct = fields.Float(
        string="Share %", digits=(16, 2), default=100.0,
        help="Share of the order this line applies to, e.g. the share of a colourway. 100 = every piece.",
    )
    cost_pc = fields.Float(string="Cost / pc", digits=(16, 4), compute="_compute_cost_pc", store=True)

    @api.depends("product_id")
    def _compute_uom_id(self):
        for line in self:
            if line.product_id and not line.uom_id:
                line.uom_id = line.product_id.uom_po_id or line.product_id.uom_id

    @api.onchange("product_id")
    def _onchange_product_price(self):
        for line in self:
            if line.product_id and not line.price_unit:
                seller = line.product_id.seller_ids[:1]
                line.price_unit = seller.price if seller else line.product_id.standard_price

    @api.depends("consumption", "wastage_pct", "price_unit", "share_pct")
    def _compute_cost_pc(self):
        formula = self.env["garment.cost.sheet"]._formula_material_cost_pc
        for line in self:
            line.cost_pc = formula(line.consumption, line.wastage_pct, line.price_unit, line.share_pct)

    @api.constrains("consumption", "wastage_pct", "price_unit", "share_pct")
    def _check_values(self):
        for line in self:
            if min(line.consumption, line.wastage_pct, line.price_unit, line.share_pct) < 0:
                raise ValidationError(_("Consumption, wastage, price and share cannot be negative."))
            if line.share_pct > 100:
                raise ValidationError(_("A share of the order cannot be above 100 %."))


class GarmentCostSheetProcess(models.Model):
    _name = "garment.cost.sheet.process"
    _description = "Cost Sheet Process Line"
    _order = "sheet_id, sequence, id"

    sheet_id = fields.Many2one("garment.cost.sheet", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="sheet_id.company_id", store=True)
    currency_id = fields.Many2one(related="sheet_id.currency_id")
    sequence = fields.Integer(default=10)
    process_type = fields.Selection(
        [
            ("print", "Printing"),
            ("embroidery", "Embroidery"),
            ("wash", "Washing"),
            ("jobwork", "Job Work"),
            ("testing", "Testing"),
            ("packing", "Packing"),
            ("other", "Other"),
        ],
        string="Process", required=True, default="print",
    )
    name = fields.Char(string="Description")
    partner_id = fields.Many2one("res.partner", string="Done By", help="Job-work vendor, empty = in house.")
    charge_basis = fields.Selection(
        [("piece", "Per piece"), ("order", "For the whole order")],
        string="Charged", required=True, default="piece",
    )
    cost = fields.Float(string="Cost", digits=(16, 2))
    cost_pc = fields.Float(string="Cost / pc", digits=(16, 4), compute="_compute_cost_pc", store=True)

    @api.depends("cost", "charge_basis", "sheet_id.quantity_basis")
    def _compute_cost_pc(self):
        formula = self.env["garment.cost.sheet"]._formula_process_cost_pc
        for line in self:
            line.cost_pc = formula(line.cost, line.charge_basis, line.sheet_id.quantity_basis)

    @api.constrains("cost")
    def _check_cost(self):
        if any(line.cost < 0 for line in self):
            raise ValidationError(_("A process cost cannot be negative."))
