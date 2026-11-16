from odoo import api, fields, models

OPERATION_SECTIONS = [
    ("preparation", "Preparation"),
    ("front", "Front"),
    ("back", "Back"),
    ("sleeve", "Sleeve / Leg"),
    ("assembly", "Assembly"),
    ("finishing", "Finishing"),
]


class GarmentOperation(models.Model):
    _name = "garment.operation"
    _description = "Sewing Operation"
    _order = "type_id, sequence, code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    type_id = fields.Many2one("garment.type", string="Garment Type", index=True,
                              help="Garment type whose standard bulletin this operation belongs to.")
    section = fields.Selection(OPERATION_SECTIONS, default="assembly")
    machine_type_id = fields.Many2one("garment.machine.type", string="Machine Type")
    default_sam = fields.Float(string="Default SAM", digits=(16, 3))
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "Operation codes must be unique."),
        ("default_sam_positive", "CHECK(default_sam >= 0)", "Default SAM cannot be negative."),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for operation in self:
            operation.display_name = (
                f"[{operation.code}] {operation.name}" if operation.code else operation.name)
