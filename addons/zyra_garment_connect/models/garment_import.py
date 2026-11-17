import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

IMPORT_TARGETS = [("rolls", "Fabric Rolls"), ("rosters", "Rosters (Employees)"), ("orders", "Production Orders")]
TARGET_MODEL = {"rolls": "stock.lot", "rosters": "hr.employee", "orders": "garment.order"}
TARGET_COLUMNS = {
    "rolls": "roll, product, dye_lot, shade_group, shrinkage_group, width_cm, gsm",
    "rosters": "name, job_title, department, work_email",
    "orders": "buyer, style, buyer_po, ex_factory_date, business_model",
}


class _DryRunRollback(Exception):
    """Raised inside a savepoint to undo a dry-run create."""


class GarmentImport(models.Model):
    _name = "garment.import"
    _description = "Garment CSV Import"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(default="/", readonly=True, copy=False)
    target = fields.Selection(IMPORT_TARGETS, string="Import", required=True, default="rolls")
    columns_hint = fields.Char(string="Columns", compute="_compute_columns_hint")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    file = fields.Binary(string="CSV File", attachment=False)
    filename = fields.Char()
    state = fields.Selection([("draft", "Uploaded"), ("checked", "Checked"), ("done", "Applied")],
                             default="draft", required=True, tracking=True, copy=False)
    line_ids = fields.One2many("garment.import.line", "import_id", string="Rows")
    row_count = fields.Integer(string="Rows Read", compute="_compute_counts")
    create_count = fields.Integer(string="Create", compute="_compute_counts")
    update_count = fields.Integer(string="Update", compute="_compute_counts")
    error_count = fields.Integer(string="Skip", compute="_compute_counts")
    created_count = fields.Integer(string="Written", compute="_compute_counts")

    @api.depends("target")
    def _compute_columns_hint(self):
        for imp in self:
            imp.columns_hint = TARGET_COLUMNS.get(imp.target, "")

    @api.depends("line_ids.status")
    def _compute_counts(self):
        for imp in self:
            imp.row_count = len(imp.line_ids)
            imp.create_count = len(imp.line_ids.filtered(lambda l: l.status in ("create", "created")))
            imp.update_count = len(imp.line_ids.filtered(lambda l: l.status in ("update", "updated")))
            imp.error_count = len(imp.line_ids.filtered(lambda l: l.status == "skip"))
            imp.created_count = len(imp.line_ids.filtered(lambda l: l.status in ("created", "updated")))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("garment.import") or "/"
        return super().create(vals_list)

    # ------------------------------------------------------------ parsing
    def _garment_rows(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_("Attach a CSV file first."))
        raw = base64.b64decode(self.file)
        text = raw.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for row in reader:
            clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if any(clean.values()):
                rows.append(clean)
        if not rows:
            raise UserError(_("The file has no data rows. Expected columns: %s", TARGET_COLUMNS[self.target]))
        return rows

    def _garment_process(self, dry_run, skip_rows=()):
        self.ensure_one()
        rows = self._garment_rows()
        Model = self.env[TARGET_MODEL[self.target]].with_company(self.company_id)
        vals_fn = getattr(self, "_garment_vals_%s" % self.target)
        results = []
        for idx, row in enumerate(rows, start=2):  # row 1 is the header
            res = {"row_no": idx, "data": ", ".join("%s=%s" % (k, v) for k, v in row.items() if v)}
            if idx in skip_rows:
                res.update(status="skip", message=_("Skipped: the dry run refused this row"))
                results.append(res)
                continue
            try:
                vals = vals_fn(row)
                existing = self._garment_find_existing(Model, vals)
                if dry_run:
                    try:
                        with self.env.cr.savepoint():
                            existing.write(vals) if existing else Model.create(vals)
                            raise _DryRunRollback()
                    except _DryRunRollback:
                        pass
                    res.update(status="update" if existing else "create",
                               message=_("%s exists: it will be updated", existing.display_name) if existing
                               else False)
                else:
                    with self.env.cr.savepoint():
                        if existing:
                            existing.write(vals)
                            rec = existing
                        else:
                            rec = Model.create(vals)
                    res.update(status="updated" if existing else "created", message=rec.display_name,
                               res_id=rec.id)
            except (UserError, ValidationError, ValueError) as e:
                res.update(status="skip", message=str(e.args[0] if e.args else e))
            except Exception as e:  # database constraint (unique, not null): show it on the row
                res.update(status="skip", message=str(e).splitlines()[0][:250])
            results.append(res)
        self.env.invalidate_all()
        self.line_ids.unlink()
        self.write({"line_ids": [fields.Command.create(r) for r in results]})

    def action_dry_run(self):
        """Check every row as if importing, then undo it all: nothing is written to the target."""
        for imp in self:
            if imp.state == "done":
                raise UserError(_("%s is already imported.", imp.name))
            imp._garment_process(dry_run=True)
            imp.state = "checked"

    def action_apply(self):
        """Write the rows the dry run accepted; rows marked Skip are left out."""
        for imp in self:
            if imp.state != "checked":
                raise UserError(_("Run the dry run first and check the rows."))
            skip_rows = set(imp.line_ids.filtered(lambda l: l.status == "skip").mapped("row_no"))
            imp._garment_process(dry_run=False, skip_rows=skip_rows)
            imp.state = "done"

    def _garment_find_existing(self, Model, vals):
        """Record the row updates instead of creating: same roll no. + fabric, or same employee name."""
        if self.target == "rolls":
            return Model.search([("name", "=", vals["name"]), ("product_id", "=", vals["product_id"]),
                                 ("company_id", "in", [vals["company_id"], False])], limit=1)
        if self.target == "rosters":
            return Model.search([("name", "=", vals["name"])], limit=1)
        return Model.browse()

    def action_reset(self):
        self.line_ids.unlink()
        self.write({"state": "draft"})

    # ------------------------------------------------------------ row -> values (also used by POST in the API)
    @api.model
    def _garment_float(self, value, label):
        if not value:
            return 0.0
        try:
            return float(value)
        except ValueError:
            raise ValidationError(_("%(label)s '%(v)s' is not a number.", label=label, v=value))

    @api.model
    def _garment_vals_rolls(self, row):
        if not row.get("roll"):
            raise ValidationError(_("Column 'roll' (roll number) is empty."))
        product_ref = row.get("product")
        product = self.env["product.product"].search(
            ["|", ("default_code", "=", product_ref), ("name", "=", product_ref)], limit=1) if product_ref else False
        if not product:
            raise ValidationError(_("No fabric product '%s'.", product_ref or ""))
        return {
            "name": row["roll"], "product_id": product.id, "is_fabric_roll": True,
            "company_id": self.env.company.id,
            "dye_lot": row.get("dye_lot") or False, "shade_group": row.get("shade_group") or False,
            "shrinkage_group": row.get("shrinkage_group") or False,
            "width_cm": self._garment_float(row.get("width_cm"), "width_cm"),
            "gsm": self._garment_float(row.get("gsm"), "gsm"),
        }

    @api.model
    def _garment_vals_rosters(self, row):
        if not row.get("name"):
            raise ValidationError(_("Column 'name' is empty."))
        vals = {"name": row["name"], "job_title": row.get("job_title") or False,
                "work_email": row.get("work_email") or False, "company_id": self.env.company.id}
        if row.get("department"):
            dept = self.env["hr.department"].search([("name", "=", row["department"])], limit=1)
            if not dept:
                raise ValidationError(_("No department '%s'.", row["department"]))
            vals["department_id"] = dept.id
        return vals

    @api.model
    def _garment_vals_orders(self, row):
        buyer = self.env["res.partner"].search([
            ("is_garment_buyer", "=", True), "|", ("buyer_code", "=", row.get("buyer")),
            ("name", "=", row.get("buyer"))], limit=1) if row.get("buyer") else False
        if not buyer:
            raise ValidationError(_("No buyer '%s'.", row.get("buyer") or ""))
        style = self.env["garment.style"].search([
            "|", ("code", "=", row.get("style")), ("name", "=", row.get("style"))], limit=1) \
            if row.get("style") else False
        if not style:
            raise ValidationError(_("No style '%s'.", row.get("style") or ""))
        if not row.get("ex_factory_date"):
            raise ValidationError(_("Column 'ex_factory_date' (YYYY-MM-DD) is empty."))
        try:
            ex_date = fields.Date.to_date(row["ex_factory_date"])
        except ValueError:
            raise ValidationError(_("ex_factory_date '%s' is not a date (YYYY-MM-DD).", row["ex_factory_date"]))
        vals = {"buyer_id": buyer.id, "style_id": style.id, "buyer_po": row.get("buyer_po") or False,
                "ex_factory_date": ex_date}
        if row.get("business_model"):
            if row["business_model"] not in ("fob", "cmt"):
                raise ValidationError(_("business_model must be fob or cmt."))
            vals["business_model"] = row["business_model"]
        return vals


class GarmentImportLine(models.Model):
    _name = "garment.import.line"
    _description = "Garment CSV Import Row"
    _order = "import_id, row_no"

    import_id = fields.Many2one("garment.import", required=True, ondelete="cascade", index=True)
    row_no = fields.Integer(string="Row")
    data = fields.Char(string="Values")
    status = fields.Selection([("create", "Create"), ("update", "Update"), ("skip", "Skip"),
                               ("created", "Created"), ("updated", "Updated")], string="Action", required=True)
    message = fields.Char(string="Note")
    res_id = fields.Integer(string="Record ID")
