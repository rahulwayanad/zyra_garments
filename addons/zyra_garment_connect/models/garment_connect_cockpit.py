from datetime import timedelta

from markupsafe import Markup, escape

from odoo import _, api, fields, models


def _count(env, model, domain=None):
    """Soft count: 0 when the model's module is not installed."""
    if model not in env:
        return 0
    Model = env[model].sudo()
    domain = [d for d in (domain or []) if not isinstance(d, tuple) or d[0].split(".")[0] in Model._fields]
    return Model.search_count(domain)


class GarmentFirstSteps(models.TransientModel):
    """First Steps checklist (screen 121): from an empty database to the first scanned bundle."""
    _name = "garment.first.steps"
    _description = "Garment First Steps"

    steps_done = fields.Integer(compute="_compute_steps")
    steps_total = fields.Integer(compute="_compute_steps")
    steps_label = fields.Char(string="Steps Done", compute="_compute_steps")
    steps_html = fields.Html(compute="_compute_steps", sanitize=False)

    @api.model
    def _garment_steps(self):
        env = self.env
        garment_groups = env.ref("zyra_garment_base.module_category_garment", raise_if_not_found=False)
        role_users = env["res.users"].sudo().search_count([
            ("share", "=", False), ("groups_id.category_id", "=", garment_groups.id)]) if garment_groups else 0
        return [
            (_("Install and run Factory Setup"), _count(env, "garment.size.range") > 0
             and _count(env, "garment.type") > 0, "zyra_garment_base.action_garment_size_range"),
            (_("Give each user a role"), role_users > 1, "base.action_res_users"),
            (_("Import buyers, fabrics and trims"), _count(env, "res.partner", [("is_garment_buyer", "=", True)]) > 0
             and _count(env, "product.product") > 0, "zyra_garment_connect.action_garment_import"),
            (_("Import styles and operations"), _count(env, "garment.style") > 0
             and _count(env, "garment.operation") > 0, "zyra_garment_connect.action_garment_import"),
            (_("Create sewing lines and operator badges"), _count(env, "garment.line") > 0
             and _count(env, "hr.employee") > 0, "hr.open_view_employee_list_my"),
            (_("Approve the first operation bulletin"),
             _count(env, "garment.bulletin", [("state", "=", "approved")]) > 0, None),
            (_("Confirm a production order"), _count(env, "garment.order", [
                ("state", "not in", ("draft", "cancel"))]) > 0, "zyra_garment_merch.action_garment_order"),
            (_("Propose its cut plan and print bundle tickets"), _count(env, "garment.bundle") > 0, None),
            (_("Scan the first coupon"), _count(env, "garment.bundle.coupon", [("scanned_at", "!=", False)]) > 0,
             None),
        ]

    def _compute_steps(self):
        steps = self._garment_steps()
        done = sum(1 for _n, ok, _a in steps if ok)
        rows = []
        for name, ok, action in steps:
            action_rec = self.env.ref(action, raise_if_not_found=False) if action else False
            link = Markup('<a href="/odoo/action-%s">%s &#8594;</a>') % (action_rec.id, _("Open")) \
                if action_rec else Markup("")
            rows.append(Markup(
                '<tr><td style="width:32px">%s</td><td>%s</td><td class="text-end">%s</td></tr>') % (
                Markup('<i class="fa fa-check-circle text-success fa-lg"/>') if ok
                else Markup('<i class="fa fa-circle-o text-muted fa-lg"/>'),
                Markup("<s class='text-muted'>%s</s>") % name if ok else Markup("<b>%s</b>") % name,
                _("Done") if ok else link))
        html = Markup('<table class="table o_garment_first_steps">%s</table>') % Markup("").join(rows)
        for rec in self:
            rec.steps_done = done
            rec.steps_total = len(steps)
            rec.steps_label = "%s / %s" % (done, len(steps))
            rec.steps_html = html


class GarmentConnectCockpit(models.TransientModel):
    """Connect cockpit (screen 20): API calls, refusals, webhook retries."""
    _name = "garment.connect.cockpit"
    _description = "Garment Connect Cockpit"

    api_calls_30d = fields.Integer(string="API Calls, 30 d", compute="_compute_cockpit")
    refused_30d = fields.Integer(string="Refused", compute="_compute_cockpit")
    webhook_retries = fields.Integer(string="Webhook Retries", compute="_compute_cockpit")
    portal_views = fields.Integer(string="Portal Views", compute="_compute_cockpit")
    documents_to_review = fields.Integer(string="Documents to Review", compute="_compute_cockpit")
    headline = fields.Html(compute="_compute_cockpit", sanitize=False)
    delivery_ids = fields.Many2many("garment.webhook.delivery", compute="_compute_cockpit",
                                    string="Webhook Deliveries")
    key_ids = fields.Many2many("garment.api.key", compute="_compute_cockpit", string="Calls by Key")

    def _compute_cockpit(self):
        since = fields.Datetime.now() - timedelta(days=30)
        Call = self.env["garment.api.call"]
        calls = Call.search_count([("create_date", ">=", since)])
        refused = Call.search_count([("create_date", ">=", since), ("status", ">=", 400)])
        retrying = self.env["garment.webhook.delivery"].search_count([("state", "=", "retrying")])
        latest = self.env["garment.webhook.delivery"].search([], limit=10)
        for rec in self:
            rec.api_calls_30d = calls
            rec.refused_30d = refused
            rec.webhook_retries = retrying
            rec.portal_views = 0  # owned by zyra_garment_portal (not built yet)
            rec.documents_to_review = 0  # optional AI document reading (not built)
            rec.headline = Markup(_("The API answered <b>%(calls)s</b> calls in 30 days; "
                                    "<b class='text-warning'>%(refused)s</b> were refused and "
                                    "<b>%(retry)s webhooks</b> are retrying.")) % {
                "calls": escape("{:,}".format(calls)), "refused": refused, "retry": retrying}
            rec.delivery_ids = latest
            rec.key_ids = self.env["garment.api.key"].search([("state", "=", "active")])
