from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _carton_range(cartons):
    numbers = sorted(cartons.mapped("number"))
    if not numbers:
        return ""
    if len(numbers) == 1:
        return "CTN %03d" % numbers[0]
    return "CTN %03d–%03d" % (numbers[0], numbers[-1])


class GarmentCarton(models.Model):
    """One export carton: content by colour × size, weights, volume and its SSCC-18 label."""

    _name = "garment.carton"
    _description = "Carton"
    _order = "plan_id desc, number, id"
    _check_company_auto = True

    name = fields.Char(string="Carton", compute="_compute_name", store=True)
    number = fields.Integer(string="Carton No.", required=True)
    plan_id = fields.Many2one("garment.pack.plan", string="Pack Plan", required=True, ondelete="cascade",
                              index=True, check_company=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    order_id = fields.Many2one(related="plan_id.order_id", string="Order", store=True, index=True)
    order_name = fields.Char(related="order_id.name", string="Order No.")
    buyer_id = fields.Many2one(related="plan_id.buyer_id", string="Buyer", store=True)
    line_ids = fields.One2many("garment.carton.line", "carton_id", string="Content Lines")
    colour_id = fields.Many2one("garment.colour", string="Colour", compute="_compute_content", store=True,
                                help="Empty when the carton mixes colourways.")
    content = fields.Char(string="Content", compute="_compute_content", store=True)
    pieces = fields.Integer(string="Pieces", compute="_compute_content", store=True)
    net_weight = fields.Float(string="Net kg", digits=(16, 2), compute="_compute_weights", store=True)
    gross_weight = fields.Float(string="Gross kg", digits=(16, 2), compute="_compute_weights", store=True)
    cbm = fields.Float(string="CBM", digits=(16, 3), related="plan_id.carton_cbm", store=True)
    sscc = fields.Char(string="SSCC-18", copy=False, index=True, readonly=True)
    sscc_display = fields.Char(string="SSCC", compute="_compute_sscc_display")
    shipment_id = fields.Many2one("garment.shipment", string="Shipment", index=True, copy=False,
                                  ondelete="set null", check_company=True)
    state = fields.Selection([("planned", "Planned"), ("packed", "Packed"), ("shipped", "Shipped")],
                             default="planned", required=True, index=True, copy=False)
    date_packed = fields.Datetime(string="Packed On", copy=False, readonly=True)
    stock_posted = fields.Boolean(string="Posted to Stock", copy=False, readonly=True)

    _sql_constraints = [
        ("sscc_uniq", "unique(sscc)", "An SSCC is used on one carton only."),
        ("number_uniq", "unique(plan_id, number)", "A carton number appears once in a pack plan."),
    ]

    @api.depends("number")
    def _compute_name(self):
        for carton in self:
            carton.name = "CTN %03d" % carton.number

    @api.depends("line_ids.qty", "line_ids.colour_id", "line_ids.size_id")
    def _compute_content(self):
        for carton in self:
            lines = carton.line_ids.filtered(lambda l: l.qty > 0).sorted(
                lambda l: (l.colour_id.name or "", l.size_id.sequence, l.size_id.id))
            colours = lines.mapped("colour_id")
            carton.colour_id = colours if len(colours) == 1 else False
            if len(colours) > 1:
                carton.content = " · ".join("%s %s %s" % (l.colour_id.name, l.size_id.name, l.qty) for l in lines)
            else:
                carton.content = " · ".join("%s %s" % (l.size_id.name, l.qty) for l in lines)
            carton.pieces = sum(lines.mapped("qty"))

    @api.depends("pieces", "plan_id.net_weight_per_piece", "plan_id.empty_carton_weight")
    def _compute_weights(self):
        for carton in self:
            carton.net_weight = carton.pieces * carton.plan_id.net_weight_per_piece
            carton.gross_weight = carton.net_weight + carton.plan_id.empty_carton_weight

    @api.depends("sscc")
    def _compute_sscc_display(self):
        for carton in self:
            carton.sscc_display = "(00) %s" % carton.sscc if carton.sscc else False

    def write(self, vals):
        if "line_ids" in vals and self.filtered(lambda c: c.state != "planned"):
            raise UserError(_("The content of a packed carton cannot change. Unpack it first."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda c: c.state != "planned"):
            raise UserError(_("Only planned cartons can be deleted."))
        return super().unlink()

    # ------------------------------------------------------------------ SSCC
    def _assign_sscc(self):
        Sequence = self.env["ir.sequence"].sudo()
        for carton in self.filtered(lambda c: not c.sscc).sorted("number"):
            serial = Sequence.next_by_code("garment.carton.sscc")
            carton.sscc = carton.company_id._garment_make_sscc(serial)
        return True

    @api.model
    def _normalise_scan(self, code):
        """Barcode scanners send the SSCC with or without the (00) application identifier."""
        code = (code or "").strip().replace("(00)", "").replace(" ", "")
        if len(code) == 20 and code.startswith("00"):
            code = code[2:]
        return code


    # ------------------------------------------------------------------ packing list
    @api.model
    def _packing_list_rows(self, cartons):
        """{'sizes': sizes, 'rows': [...], totals}: consecutive cartons with the same colour and size content
        share one row ("1 – 6")."""
        cartons = cartons.sorted(lambda c: (c.plan_id.id, c.number))
        sizes = cartons.line_ids.mapped("size_id").sorted(lambda s: (s.sequence, s.id))
        rows = []
        for carton in cartons:
            key = (carton.plan_id.id, tuple(sorted((l.colour_id.id, l.size_id.id, l.qty) for l in carton.line_ids)))
            by_size = defaultdict(int)
            for line in carton.line_ids:
                by_size[line.size_id.id] += line.qty
            last = rows[-1] if rows else None
            if last and last["key"] == key and last["last"] == carton.number - 1:
                last["last"] = carton.number
                last["count"] += 1
                continue
            rows.append({
                "key": key, "first": carton.number, "last": carton.number, "count": 1,
                "colour": carton.colour_id.name or _("Mixed"),
                "by_size": dict(by_size), "pcs": carton.pieces,
                "net": carton.net_weight, "gross": carton.gross_weight,
            })
        for row in rows:
            row["range"] = str(row["first"]) if row["count"] == 1 else "%s – %s" % (row["first"], row["last"])
            row["pieces"] = row["pcs"] * row["count"]
        return {
            "sizes": sizes,
            "rows": rows,
            "pieces": sum(cartons.mapped("pieces")),
            "cartons": len(cartons),
            "net": sum(cartons.mapped("net_weight")),
            "gross": sum(cartons.mapped("gross_weight")),
            "cbm": sum(cartons.mapped("cbm")),
        }

    # ------------------------------------------------------------------ packing
    def action_pack(self):
        """Pack planned cartons: SSCC assigned, and the pieces posted to the order as 'packed'
        (one posting per grid cell and pack plan, ref = plan and carton range)."""
        cartons = self.filtered(lambda c: c.state == "planned")
        if not cartons:
            raise UserError(_("Only planned cartons can be packed."))
        if cartons.filtered(lambda c: not c.pieces):
            raise UserError(_("An empty carton cannot be packed."))
        cartons._assign_sscc()
        for plan in cartons.mapped("plan_id"):
            plan_cartons = cartons.filtered(lambda c: c.plan_id == plan)
            plan._garment_post_cells(plan_cartons, "packed", 1, "%s %s" % (plan.name, _carton_range(plan_cartons)))
        cartons.write({"state": "packed", "date_packed": fields.Datetime.now()})
        return True

    def action_unpack(self):
        cartons = self.filtered(lambda c: c.state == "packed")
        if cartons.filtered("stock_posted"):
            raise UserError(_("A carton already posted to stock cannot be unpacked."))
        if cartons.filtered("shipment_id"):
            raise UserError(_("Take the carton off its shipment before unpacking it."))
        for plan in cartons.mapped("plan_id"):
            plan_cartons = cartons.filtered(lambda c: c.plan_id == plan)
            plan._garment_post_cells(plan_cartons, "packed", -1,
                                     _("%(plan)s %(range)s unpacked", plan=plan.name, range=_carton_range(plan_cartons)))
        cartons.write({"state": "planned", "date_packed": False})
        return True


class GarmentCartonLine(models.Model):
    _name = "garment.carton.line"
    _description = "Carton Content"
    _order = "carton_id, colour_id, size_sequence, id"

    carton_id = fields.Many2one("garment.carton", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="carton_id.company_id", store=True)
    colour_id = fields.Many2one("garment.colour", string="Colour", required=True)
    size_id = fields.Many2one("garment.size", string="Size", required=True)
    size_sequence = fields.Integer(related="size_id.sequence", store=True)
    qty = fields.Integer(string="Pieces", required=True)

    _sql_constraints = [
        ("qty_positive", "CHECK(qty >= 0)", "Carton content cannot be negative."),
    ]
