from odoo import api, fields, models


class ZyraTechpack(models.Model):
    _inherit = "zyra.techpack"

    cost_sheet_ids = fields.One2many("garment.cost.sheet", "techpack_id", string="Cost Sheets")
    cost_sheet_count = fields.Integer(compute="_compute_cost_sheet_count", string="Cost Sheet Count")
    approved_cost_sheet_id = fields.Many2one(
        "garment.cost.sheet", string="Approved Cost Sheet", readonly=True, copy=False, index=True,
        help="Written when a cost sheet of this revision is approved; follows newer approved versions.",
    )
    planned_currency_id = fields.Many2one(related="approved_cost_sheet_id.currency_id", string="Cost Currency")
    planned_material_cost = fields.Monetary(
        related="approved_cost_sheet_id.material_cost_pc", string="Planned Material / pc",
        currency_field="planned_currency_id", store=True,
    )
    planned_making_cost = fields.Monetary(
        related="approved_cost_sheet_id.making_cost_pc", string="Planned Making / pc",
        currency_field="planned_currency_id", store=True,
    )
    planned_cost_per_piece = fields.Monetary(
        related="approved_cost_sheet_id.total_cost_pc", string="Planned Cost / pc",
        currency_field="planned_currency_id", store=True,
        help="Material + processes + making from the approved cost sheet.",
    )
    planned_fob_price = fields.Monetary(
        related="approved_cost_sheet_id.fob_price", string="Planned FOB Price",
        currency_field="planned_currency_id", store=True,
    )
    planned_margin_pct = fields.Float(
        related="approved_cost_sheet_id.margin_pct", string="Planned Margin %", store=True,
    )

    @api.depends("cost_sheet_ids")
    def _compute_cost_sheet_count(self):
        for techpack in self:
            techpack.cost_sheet_count = len(techpack.cost_sheet_ids)

    def action_view_cost_sheets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_costing.action_garment_cost_sheet")
        action["domain"] = [("techpack_id", "=", self.id)]
        action["context"] = {"default_techpack_id": self.id, "search_default_latest": 0}
        return action


class GarmentStyle(models.Model):
    _inherit = "garment.style"

    approved_cost_sheet_id = fields.Many2one(
        "garment.cost.sheet", string="Approved Cost Sheet", compute="_compute_approved_cost_sheet_id",
        help="The current tech pack's approved cost sheet, else the style's latest approved one.",
    )
    cost_sheet_count = fields.Integer(compute="_compute_approved_cost_sheet_id", string="Cost Sheet Count")

    def _compute_approved_cost_sheet_id(self):
        Sheet = self.env["garment.cost.sheet"]
        for style in self:
            sheet = style.current_techpack_id.approved_cost_sheet_id
            if not sheet and isinstance(style.id, int):
                sheet = Sheet.search([("style_id", "=", style.id), ("state", "=", "approved")],
                                     order="approved_date desc, id desc", limit=1)
            style.approved_cost_sheet_id = sheet
            style.cost_sheet_count = Sheet.search_count([("style_id", "=", style.id)]) \
                if isinstance(style.id, int) else 0

    def action_view_cost_sheets(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_costing.action_garment_cost_sheet")
        action["domain"] = [("style_id", "=", self.id)]
        action["context"] = {"default_techpack_id": self.current_techpack_id.id or
                             self.techpack_ids[:1].id}
        return action
