from odoo import _, fields, models
from odoo.exceptions import UserError


class GarmentCartonPackWizard(models.TransientModel):
    """Pack / Scan Cartons: scan a carton label (SSCC or carton no.) or pack the next planned cartons."""

    _name = "garment.carton.pack.wizard"
    _description = "Pack / Scan Cartons"

    plan_id = fields.Many2one("garment.pack.plan", required=True)
    scan = fields.Char(string="Scan carton", help="SSCC label (with or without (00)) or the carton number.")
    count = fields.Integer(string="Or pack the next … cartons", default=1)
    last_result = fields.Char(readonly=True)
    cartons_packed = fields.Integer(related="plan_id.cartons_packed")
    cartons_planned = fields.Integer(related="plan_id.cartons_planned")

    def _find_carton(self, code):
        Carton = self.env["garment.carton"]
        domain = [("plan_id", "=", self.plan_id.id)]
        normal = Carton._normalise_scan(code)
        carton = Carton.search(domain + [("sscc", "=", normal)], limit=1) if normal else Carton
        if not carton:
            digits = "".join(ch for ch in code if ch.isdigit())
            if digits and len(digits) < 8:
                carton = Carton.search(domain + [("number", "=", int(digits))], limit=1)
        return carton

    def action_pack(self):
        self.ensure_one()
        plan = self.plan_id
        if self.scan:
            carton = self._find_carton(self.scan)
            if not carton:
                raise UserError(_("No carton %(code)s in %(plan)s.", code=self.scan, plan=plan.name))
            if carton.state != "planned":
                raise UserError(_("%(carton)s is already %(state)s.", carton=carton.name,
                                  state=dict(carton._fields["state"].selection)[carton.state].lower()))
            cartons = carton
        else:
            if self.count <= 0:
                raise UserError(_("Scan a carton or give the number of cartons to pack."))
            if not plan.carton_ids:
                plan.action_generate_cartons()
            cartons = plan.carton_ids.filtered(lambda c: c.state == "planned").sorted("number")[:self.count]
            if not cartons:
                raise UserError(_("Every carton of %s is packed. Generate more cartons first.", plan.name))
        cartons.action_pack()
        result = _("Packed %(cartons)s (%(pieces)s pieces).", cartons=", ".join(cartons.mapped("name")),
                   pieces=sum(cartons.mapped("pieces")))
        if self.scan:
            # stay open for the next scan
            wizard = self.create({"plan_id": plan.id, "last_result": result, "count": 0})
            return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": wizard.id,
                    "view_mode": "form", "target": "new", "name": _("Pack / Scan Cartons")}
        plan.message_post(body=result)
        return {"type": "ir.actions.act_window_close"}
