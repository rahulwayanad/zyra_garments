from odoo import api, fields, models


class GarmentOrder(models.Model):
    _inherit = "garment.order"

    inspection_ids = fields.One2many("garment.inspection", "order_id", string="Inspections")
    inspection_count = fields.Integer(compute="_compute_inspection_count")
    final_inspection_id = fields.Many2one("garment.inspection", string="Latest Final Inspection",
                                          compute="_compute_final_inspection", store=True)
    # Contract with zyra_garment_shipping (soft read): do not rename.
    final_inspection_state = fields.Selection(
        [("none", "Not inspected"), ("passed", "Passed"), ("failed", "Failed")],
        string="Final Inspection", compute="_compute_final_inspection", store=True, default="none")
    final_passed = fields.Boolean(string="Final Inspection Passed", compute="_compute_final_inspection", store=True,
                                  help="True when the latest completed final inspection of the order passed "
                                       "(or was accepted under concession). A failed final blocks shipment.")

    @api.depends("inspection_ids")
    def _compute_inspection_count(self):
        for order in self:
            order.inspection_count = len(order.inspection_ids)

    @api.depends("inspection_ids.kind", "inspection_ids.state", "inspection_ids.result", "inspection_ids.date")
    def _compute_final_inspection(self):
        for order in self:
            finals = order.inspection_ids.filtered(
                lambda i: i.kind == "final" and i.state == "completed"
                and i.result in ("passed", "failed", "concession"))
            latest = finals.sorted(lambda i: (i.date, i.id))[-1:] if finals else finals
            order.final_inspection_id = latest
            if not latest:
                order.final_inspection_state = "none"
            elif latest.result in ("passed", "concession"):
                order.final_inspection_state = "passed"
            else:
                order.final_inspection_state = "failed"
            order.final_passed = order.final_inspection_state == "passed"

    def action_view_inspections(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("zyra_garment_quality.action_garment_inspection")
        action.update({"domain": [("order_id", "=", self.id)], "context": {"default_order_id": self.id}})
        return action
