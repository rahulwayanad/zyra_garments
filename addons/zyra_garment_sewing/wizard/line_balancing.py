import math

from odoo import Command, api, fields, models


class GarmentLineBalancing(models.TransientModel):
    """Line balancing (screen 55). Rules:
    pitch time = total SAM ÷ operators; operators needed per operation = SAM ÷ pitch time, allocated
    rounded up to whole operators (min 1, later trimmed to the line's operators where possible);
    station cycle = SAM ÷ allocated; bottleneck = longest cycle; balanced output / hour = 60 ÷ bottleneck cycle;
    target output / hour = operators × 60 ÷ total SAM; balance loss % = (1 − total SAM ÷ (allocated operators
    × bottleneck cycle)) × 100."""
    _name = "garment.line.balancing"
    _description = "Line Balancing"

    bulletin_id = fields.Many2one("garment.bulletin", required=True)
    line_id = fields.Many2one("garment.line", string="Line")
    operators = fields.Integer(required=True, default=20)
    total_sam = fields.Float(related="bulletin_id.total_sam", digits=(16, 3))
    pitch_time = fields.Float(digits=(16, 3), compute="_compute_balance")
    target_output = fields.Integer(string="Target / Hour", compute="_compute_balance")
    balanced_output = fields.Integer(string="Balanced / Hour", compute="_compute_balance")
    balance_loss = fields.Float(string="Balance Loss %", digits=(16, 1), compute="_compute_balance")
    operators_allocated = fields.Integer(compute="_compute_balance")
    bottleneck = fields.Char(compute="_compute_balance")
    station_ids = fields.One2many("garment.line.balancing.station", "wizard_id", compute="_compute_balance")

    @api.onchange("line_id")
    def _onchange_line(self):
        if self.line_id:
            self.operators = self.line_id.operator_count

    @api.model
    def _garment_balance(self, sams, operators):
        """Pure maths, used by the compute and the tests. ``sams``: list of SAM. Returns a dict."""
        total = sum(sams)
        if not total or operators <= 0 or not sams:
            return {"pitch": 0.0, "target": 0, "balanced": 0, "loss": 0.0, "alloc": [], "cycles": [],
                    "bottleneck": -1, "allocated": 0}
        pitch = total / operators
        alloc = [max(1, math.ceil(round(s / pitch, 6))) for s in sams]
        # trim the stations with the most slack while we use more operators than the line has
        while sum(alloc) > operators:
            candidates = [i for i, a in enumerate(alloc) if a > 1]
            if not candidates:
                break
            i = min(candidates, key=lambda k: sams[k] / (alloc[k] - 1))
            alloc[i] -= 1
        cycles = [s / a for s, a in zip(sams, alloc)]
        neck = max(range(len(cycles)), key=lambda k: cycles[k])
        allocated = sum(alloc)
        return {
            "pitch": pitch,
            "target": int(round(operators * 60 / total, 6)),
            "balanced": int(round(60 / cycles[neck], 6)),
            "loss": round((1 - total / (allocated * cycles[neck])) * 100, 1),
            "alloc": alloc, "cycles": cycles, "bottleneck": neck, "allocated": allocated,
        }

    @api.depends("bulletin_id.line_ids.sam", "operators")
    def _compute_balance(self):
        for wiz in self:
            lines = wiz.bulletin_id.line_ids
            res = self._garment_balance(lines.mapped("sam"), wiz.operators)
            wiz.pitch_time = res["pitch"]
            wiz.target_output = res["target"]
            wiz.balanced_output = res["balanced"]
            wiz.balance_loss = res["loss"]
            wiz.operators_allocated = res["allocated"]
            wiz.bottleneck = lines[res["bottleneck"]].name if res["bottleneck"] >= 0 else False
            wiz.station_ids = [Command.clear()] + [Command.create({
                "name": line.name, "sam": line.sam, "operators": res["alloc"][i], "cycle": res["cycles"][i],
                "output": int(round(60 / res["cycles"][i], 6)) if res["cycles"][i] else 0,
                "is_bottleneck": i == res["bottleneck"]}) for i, line in enumerate(lines)] if res["alloc"] else \
                [Command.clear()]

    def action_apply(self):
        self.ensure_one()
        if self.line_id:
            self.line_id.write({"current_bulletin_id": self.bulletin_id.id, "operator_count": self.operators})
        return {"type": "ir.actions.act_window_close"}


class GarmentLineBalancingStation(models.TransientModel):
    _name = "garment.line.balancing.station"
    _description = "Line Balancing Station"

    wizard_id = fields.Many2one("garment.line.balancing", ondelete="cascade")
    name = fields.Char(string="Operation")
    sam = fields.Float(string="SAM", digits=(16, 3))
    operators = fields.Integer()
    cycle = fields.Float(string="Cycle (min)", digits=(16, 3))
    output = fields.Integer(string="Output / Hour")
    is_bottleneck = fields.Boolean(string="Bottleneck")
