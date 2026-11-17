"""AQL sampling tables (ISO 2859-1, single sampling, normal inspection) kept as editable records.

``garment.aql.lot.range`` is Table 1 (lot size → code letter per inspection level); ``garment.aql.limit``
is Table II-A resolved for one AQL: the arrows are already followed, so each row holds the sample size,
accept and reject numbers that apply to that code letter at that AQL."""
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

LEVELS = [("I", "General I"), ("II", "General II"), ("III", "General III")]


class GarmentAqlLotRange(models.Model):
    _name = "garment.aql.lot.range"
    _description = "AQL lot size range (code letter)"
    _order = "level, lot_min"
    _rec_name = "code_letter"

    level = fields.Selection(LEVELS, string="Inspection level", required=True, default="II")
    lot_min = fields.Integer(string="Lot from", required=True)
    lot_max = fields.Integer(string="Lot to", required=True)
    code_letter = fields.Char(required=True, size=2)
    letter_sample_size = fields.Integer(string="Sample size of the letter")
    active = fields.Boolean(default=True)

    @api.constrains("lot_min", "lot_max")
    def _check_range(self):
        for rng in self:
            if rng.lot_min < 1 or rng.lot_max < rng.lot_min:
                raise ValidationError(self.env._("A lot range needs 1 ≤ from ≤ to."))
            overlap = self.search_count([
                ("id", "!=", rng.id), ("level", "=", rng.level),
                ("lot_min", "<=", rng.lot_max), ("lot_max", ">=", rng.lot_min),
            ])
            if overlap:
                raise ValidationError(self.env._("Lot ranges of one inspection level cannot overlap."))

    @api.depends("code_letter", "lot_min", "lot_max", "level")
    def _compute_display_name(self):
        for rng in self:
            rng.display_name = "%s (%s – %s, level %s)" % (rng.code_letter, rng.lot_min, rng.lot_max, rng.level)


class GarmentAqlLimit(models.Model):
    _name = "garment.aql.limit"
    _description = "AQL accept / reject numbers"
    _order = "aql, sample_size, code_letter"
    _rec_name = "code_letter"

    code_letter = fields.Char(required=True, size=2)
    aql = fields.Float(string="AQL", required=True, digits=(16, 2))
    sample_size = fields.Integer(required=True)
    accept = fields.Integer(string="Accept (Ac)", required=True)
    reject = fields.Integer(string="Reject (Re)", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("letter_aql_unique", "unique(code_letter, aql)", "One row per code letter and AQL."),
    ]

    @api.constrains("accept", "reject", "sample_size")
    def _check_numbers(self):
        for row in self:
            if row.sample_size < 1 or row.accept < 0 or row.reject != row.accept + 1:
                raise ValidationError(self.env._(
                    "An AQL row needs a sample size of at least 1 and Re = Ac + 1 (single sampling)."))

    @api.model
    def _garment_lookup(self, lot_size, aql, level="II"):
        """Sampling plan for ``lot_size`` pieces at ``aql``.

        Returns ``{'code_letter', 'sample_size', 'accept', 'reject'}``; raises ``UserError`` when the
        tables have no row for it (tables are data: fix them under Quality › Configuration)."""
        if not lot_size or lot_size < 1:
            raise UserError(self.env._("Enter the lot size first."))
        rng = self.env["garment.aql.lot.range"].search(
            [("level", "=", level), ("lot_min", "<=", lot_size), ("lot_max", ">=", lot_size)], limit=1)
        if not rng:
            raise UserError(self.env._("No AQL code letter for a lot of %(lot)s pieces (level %(level)s).",
                                       lot=lot_size, level=level))
        row = self.search([("code_letter", "=", rng.code_letter), ("aql", "=", aql)], limit=1)
        if not row:
            raise UserError(self.env._("No AQL row for code letter %(letter)s at AQL %(aql)s.",
                                       letter=rng.code_letter, aql=aql))
        return {
            "code_letter": rng.code_letter,
            "sample_size": row.sample_size,
            "accept": row.accept,
            "reject": row.reject,
        }
