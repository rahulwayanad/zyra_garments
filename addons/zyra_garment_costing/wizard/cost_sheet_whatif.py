from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class GarmentCostSheetWhatIf(models.TransientModel):
    """Try other margin, efficiency or minute cost without touching the sheet."""

    _name = "garment.cost.sheet.whatif"
    _description = "Cost Sheet What If"

    sheet_id = fields.Many2one("garment.cost.sheet", required=True, readonly=True)
    currency_id = fields.Many2one(related="sheet_id.currency_id")
    sheet_state = fields.Selection(related="sheet_id.state")
    target_price = fields.Monetary(related="sheet_id.target_price")
    current_fob = fields.Monetary(related="sheet_id.fob_price", string="Current FOB")
    margin_floor_pct = fields.Float(related="sheet_id.margin_floor_pct")

    sam = fields.Float(string="SAM (min)", digits=(16, 2))
    line_efficiency = fields.Float(string="Line Efficiency %", digits=(16, 2))
    cost_per_minute = fields.Float(string="Cost per Minute", digits=(16, 4))
    margin_pct = fields.Float(string="Margin %", digits=(16, 2))

    making_cost_pc = fields.Monetary(string="Making Cost / pc", compute="_compute_result")
    fob_price = fields.Monetary(string="FOB Price", compute="_compute_result")
    fob_over_target = fields.Monetary(string="FOB over Target", compute="_compute_result")
    margin_at_target = fields.Float(
        string="Margin at Target Price %", compute="_compute_result", digits=(16, 2),
        help="Margin left if the buyer pays exactly the target price.",
    )
    below_floor = fields.Boolean(compute="_compute_result")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sheet = self.env["garment.cost.sheet"].browse(res.get("sheet_id") or self.env.context.get("default_sheet_id"))
        if sheet:
            res.update({
                "sam": sheet.sam,
                "line_efficiency": sheet.line_efficiency,
                "cost_per_minute": sheet.cost_per_minute,
                "margin_pct": sheet.margin_pct,
            })
        return res

    @api.depends("sam", "line_efficiency", "cost_per_minute", "margin_pct", "sheet_id")
    def _compute_result(self):
        Sheet = self.env["garment.cost.sheet"]
        for wiz in self:
            sheet = wiz.sheet_id
            making = Sheet._formula_making_cost(wiz.sam, wiz.cost_per_minute, wiz.line_efficiency)
            cost = sheet.material_cost_pc + sheet.process_cost_pc + making
            fob = Sheet._formula_fob_price(cost, sheet.overhead_pct, sheet.commission_pct, wiz.margin_pct)
            wiz.making_cost_pc = making
            wiz.fob_price = fob
            wiz.fob_over_target = fob - sheet.target_price if sheet.target_price else 0.0
            wiz.margin_at_target = Sheet._formula_margin_at_price(
                cost, sheet.overhead_pct, sheet.commission_pct, sheet.target_price)
            wiz.below_floor = float_compare(wiz.margin_pct, sheet.margin_floor_pct, precision_digits=2) < 0

    def action_use_target_margin(self):
        self.ensure_one()
        self.margin_pct = self.margin_at_target
        return self._reopen()

    def action_apply(self):
        self.ensure_one()
        if self.sheet_id.state != "draft":
            raise UserError(_("Only a draft cost sheet takes What If figures. Make a new version first."))
        self.sheet_id.write({
            "sam": self.sam,
            "line_efficiency": self.line_efficiency,
            "cost_per_minute": self.cost_per_minute,
            "margin_pct": self.margin_pct,
        })
        return {"type": "ir.actions.act_window_close"}

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("What If"),
        }
