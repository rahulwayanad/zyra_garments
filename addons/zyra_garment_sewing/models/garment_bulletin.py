from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.zyra_garment_base.models.garment_operation import OPERATION_SECTIONS


class GarmentBulletin(models.Model):
    """Operation bulletin of a style (screen 54): operations with section, machine, SAM, target per hour and
    piece rate."""
    _name = "garment.bulletin"
    _inherit = ["mail.thread"]
    _description = "Operation Bulletin"
    _order = "id desc"

    name = fields.Char(required=True, default=lambda self: _("New Bulletin"))
    style_id = fields.Many2one("garment.style", string="Style", required=True, index=True)
    techpack_id = fields.Many2one("zyra.techpack", string="Tech Pack")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    line_ids = fields.One2many("garment.bulletin.line", "bulletin_id", string="Operations", copy=True)
    total_sam = fields.Float(string="Total SAM", digits=(16, 3), compute="_compute_totals", store=True)
    operation_count = fields.Integer(compute="_compute_totals", store=True)
    total_piece_rate = fields.Monetary(string="Labour / Piece", compute="_compute_totals", store=True)
    active = fields.Boolean(default=True)

    @api.depends("line_ids.sam", "line_ids.piece_rate")
    def _compute_totals(self):
        for bulletin in self:
            bulletin.total_sam = sum(bulletin.line_ids.mapped("sam"))
            bulletin.operation_count = len(bulletin.line_ids)
            bulletin.total_piece_rate = sum(bulletin.line_ids.mapped("piece_rate"))

    def action_load_from_techpack(self):
        """Fill the bulletin from the tech pack operation lines (one line each)."""
        rate = float(self.env["ir.config_parameter"].sudo().get_param("zyra_garment_sewing.minute_rate", 0) or 0)
        for bulletin in self:
            techpack = bulletin.techpack_id or self.env["zyra.techpack"].search(
                [("style_id", "=", bulletin.style_id.id)], order="id desc", limit=1)
            if not techpack.operation_ids:
                raise UserError(_("The tech pack of %s has no operations.", bulletin.style_id.display_name))
            bulletin.techpack_id = techpack
            bulletin.line_ids = [Command.clear()] + [Command.create({
                "sequence": op.sequence, "operation_line_id": op.id, "name": op.name, "section": op.section,
                "machine_type_id": op.machine_type_id.id, "sam": op.sam,
                "piece_rate": round(op.sam * rate, 4)}) for op in techpack.operation_ids]
        return True

    def action_open_balancing(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Line Balancing"), "res_model": "garment.line.balancing",
            "view_mode": "form", "target": "new", "context": {"default_bulletin_id": self.id},
        }


class GarmentBulletinLine(models.Model):
    _name = "garment.bulletin.line"
    _description = "Operation Bulletin Line"
    _order = "bulletin_id, sequence, id"

    bulletin_id = fields.Many2one("garment.bulletin", required=True, ondelete="cascade", index=True)
    currency_id = fields.Many2one(related="bulletin_id.currency_id")
    sequence = fields.Integer(default=10)
    operation_line_id = fields.Many2one("zyra.techpack.operation", string="Tech Pack Operation")
    name = fields.Char(string="Operation", required=True)
    section = fields.Selection(OPERATION_SECTIONS)
    machine_type_id = fields.Many2one("garment.machine.type", string="Machine")
    sam = fields.Float(string="SAM", digits=(16, 3), required=True)
    target_per_hour = fields.Integer(string="Target / Hour", compute="_compute_target", store=True,
                                     help="60 ÷ SAM at 100 % efficiency.")
    piece_rate = fields.Float(string="Piece Rate", digits=(16, 4))

    _sql_constraints = [("sam_positive", "CHECK(sam >= 0)", "SAM cannot be negative.")]

    @api.depends("sam")
    def _compute_target(self):
        for line in self:
            line.target_per_hour = int(round(60 / line.sam, 6)) if line.sam else 0


class GarmentBulletinDemo(models.Model):
    _inherit = "garment.bulletin"

    @api.model
    def _garment_load_demo(self):
        """Demo: one bulletin per style whose tech pack has operations; first line runs the first one."""
        techpacks = self.env["zyra.techpack"].search([("operation_ids", "!=", False)], order="id")
        bulletins = self.browse()
        for techpack in techpacks:
            if self.search_count([("style_id", "=", techpack.style_id.id)]):
                continue
            bulletin = self.create({"name": _("Bulletin %s", techpack.style_id.display_name),
                                    "style_id": techpack.style_id.id, "techpack_id": techpack.id})
            bulletin.action_load_from_techpack()
            bulletins |= bulletin
        lines = self.env["garment.line"].search([], order="sequence, id")
        for line, bulletin in zip(lines, bulletins):
            line.current_bulletin_id = bulletin
        self._garment_load_demo_scans(lines[:1])
        return True

    @api.model
    def _garment_load_demo_scans(self, line):
        """Demo: issue a few cut bundles to the first line and scan their coupons with demo operators."""
        employees = self.env["hr.employee"].search([], limit=6)
        bundles = self.env["garment.bundle"].search([("stage", "=", "cut"), ("coupon_ids", "!=", False)],
                                                    limit=4, order="id")
        if not (line and employees and bundles):
            return
        bundles.action_issue(line.workcenter_id)
        Scan = self.env["garment.scan"]
        for b_index, bundle in enumerate(bundles):
            coupons = bundle.coupon_ids.sorted("sequence")
            # last bundle stays in sewing (half its coupons scanned)
            if b_index == len(bundles) - 1:
                coupons = coupons[:len(coupons) // 2]
            for c_index, coupon in enumerate(coupons):
                Scan._garment_scan(coupon.payload, employees[(b_index + c_index) % len(employees)], line=line)
        self.env["garment.line.day"].create({"line_id": line.id})
