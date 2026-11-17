import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

WEBHOOK_EVENTS = [
    ("order.confirmed", "Order confirmed"),
    ("order.shipped", "Order shipped"),
    ("bundle.cut", "Bundle cut"),
    ("bundle.scanned", "Bundle scanned"),
    ("final.failed", "Final inspection failed"),
    ("shipment.left", "Shipment left the factory"),
]
EVENT_CODES = [c for c, _l in WEBHOOK_EVENTS]
BACKOFF_MINUTES = [1, 5, 15, 60]
SIGNATURE_HEADER = "X-Zyra-Signature"


class GarmentWebhook(models.Model):
    _name = "garment.webhook"
    _description = "Garment Webhook"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    reference = fields.Char(default="/", readonly=True, copy=False)
    state = fields.Selection([("active", "Active"), ("paused", "Paused")], default="active", required=True,
                             tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    url = fields.Char(string="URL", required=True, tracking=True)
    events = fields.Char(required=True, help="Comma-separated: " + ", ".join(EVENT_CODES))
    secret = fields.Char(required=True, copy=False, groups="zyra_garment_base.group_garment_admin",
                         default=lambda self: secrets.token_hex(24),
                         help="Shared secret: the body is signed with HMAC-SHA256 using it.")
    signing_label = fields.Char(string="Signing", compute="_compute_labels")
    max_attempts = fields.Integer(string="Attempts", default=5, required=True)
    backoff_label = fields.Char(string="Back-off", compute="_compute_labels")
    delivery_ids = fields.One2many("garment.webhook.delivery", "webhook_id", string="Deliveries")
    deliveries_30d = fields.Integer(string="Deliveries, 30 Days", compute="_compute_kpis")
    failures_30d = fields.Integer(string="Failures", compute="_compute_kpis")
    retrying_count = fields.Integer(string="Retrying", compute="_compute_kpis")

    @api.constrains("events")
    def _check_events(self):
        for hook in self:
            bad = [e for e in hook._garment_event_list() if e not in EVENT_CODES]
            if bad or not hook._garment_event_list():
                raise ValidationError(_("Unknown or missing webhook event(s): %(bad)s. Use: %(ok)s",
                                        bad=", ".join(bad) or "-", ok=", ".join(EVENT_CODES)))

    @api.constrains("url")
    def _check_url(self):
        for hook in self:
            if not (hook.url or "").startswith(("https://", "http://")):
                raise ValidationError(_("The webhook URL must start with https:// (or http:// for testing)."))

    def _compute_labels(self):
        for hook in self:
            hook.signing_label = _("HMAC-SHA256 in %s", SIGNATURE_HEADER)
            steps = BACKOFF_MINUTES[:max(hook.max_attempts - 1, 0)]
            hook.backoff_label = _("%s min", ", ".join(str(m) for m in steps)) if steps else "-"

    def _compute_kpis(self):
        since = fields.Datetime.now() - timedelta(days=30)
        for hook in self:
            recent = hook.delivery_ids.filtered(lambda d: d.create_date and d.create_date >= since)
            hook.deliveries_30d = len(recent.filtered(lambda d: d.state == "delivered"))
            hook.failures_30d = len(recent.filtered(lambda d: d.state == "failed"))
            hook.retrying_count = len(hook.delivery_ids.filtered(lambda d: d.state == "retrying"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "/") == "/":
                vals["reference"] = self.env["ir.sequence"].next_by_code("garment.webhook") or "/"
        return super().create(vals_list)

    def _garment_event_list(self):
        return [e.strip() for e in (self.events or "").split(",") if e.strip()]

    # ---------------------------------------------------------------- signing
    @api.model
    def _garment_sign(self, secret, body):
        """HMAC-SHA256 hex digest of the raw body bytes, keyed with the webhook secret."""
        if isinstance(body, str):
            body = body.encode()
        return hmac.new((secret or "").encode(), body, hashlib.sha256).hexdigest()

    # ---------------------------------------------------------------- emitting
    @api.model
    def _garment_emit(self, event, data, company=None):
        """Queue one delivery per active webhook of the company subscribed to ``event``.

        Other modules call: ``if 'garment.webhook' in env: env['garment.webhook'].sudo()._garment_emit(...)``.
        Delivery happens in the cron (never inside the business transaction)."""
        if event not in EVENT_CODES:
            raise ValidationError(_("Unknown webhook event %s.", event))
        company = company or self.env.company
        hooks = self.sudo().search([("state", "=", "active"), ("company_id", "=", company.id)])
        hooks = hooks.filtered(lambda h: event in h._garment_event_list())
        body = json.dumps({"event": event, "sent_at": fields.Datetime.now().isoformat(), "data": data},
                          default=str, sort_keys=True)
        Delivery = self.env["garment.webhook.delivery"].sudo()
        deliveries = Delivery
        for hook in hooks:
            deliveries |= Delivery.create({"webhook_id": hook.id, "event": event, "payload": body,
                                           "next_attempt_at": fields.Datetime.now()})
        return deliveries

    def action_send_test(self):
        self.ensure_one()
        body = json.dumps({"event": "test", "sent_at": fields.Datetime.now().isoformat(),
                           "data": {"webhook": self.reference}})
        delivery = self.env["garment.webhook.delivery"].sudo().create({
            "webhook_id": self.id, "event": "test", "payload": body, "next_attempt_at": fields.Datetime.now()})
        delivery._garment_send()

    def action_pause(self):
        self.write({"state": "paused"})

    def action_resume(self):
        self.write({"state": "active"})

    @api.model
    def _cron_deliver(self, limit=200):
        due = self.env["garment.webhook.delivery"].sudo().search([
            ("state", "in", ("pending", "retrying")), ("next_attempt_at", "<=", fields.Datetime.now())],
            limit=limit, order="next_attempt_at, id")
        for delivery in due:
            delivery._garment_send()


class GarmentWebhookDelivery(models.Model):
    _name = "garment.webhook.delivery"
    _description = "Garment Webhook Delivery"
    _order = "id desc"

    webhook_id = fields.Many2one("garment.webhook", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="webhook_id.company_id", store=True)
    event = fields.Char(required=True)
    payload = fields.Text(required=True)
    state = fields.Selection([("pending", "Pending"), ("delivered", "Delivered"), ("retrying", "Retrying"),
                              ("failed", "Failed")], default="pending", required=True, index=True)
    attempts = fields.Integer(default=0)
    status_code = fields.Integer(string="Status")
    duration_ms = fields.Integer(string="Time (ms)")
    next_attempt_at = fields.Datetime(index=True)
    last_error = fields.Char()
    signature = fields.Char()
    result_label = fields.Char(string="Result", compute="_compute_result_label")
    create_date = fields.Datetime(string="Sent")

    def _compute_result_label(self):
        for d in self:
            if d.state == "retrying":
                d.result_label = _("Retrying (%(n)s of %(max)s)", n=d.attempts, max=d.webhook_id.max_attempts)
            else:
                d.result_label = dict(self._fields["state"].selection)[d.state]

    def _garment_send(self):
        for d in self:
            hook = d.webhook_id.sudo()
            body = d.payload.encode()
            signature = "sha256=" + hook._garment_sign(hook.secret, body)
            started = time.monotonic()
            code, error = 0, False
            try:
                resp = requests.post(hook.url, data=body, timeout=10, headers={
                    "Content-Type": "application/json", SIGNATURE_HEADER: signature,
                    "X-Zyra-Event": d.event, "X-Zyra-Delivery": str(d.id)})
                code = resp.status_code
            except requests.RequestException as e:
                error = str(e)[:250]
            attempts = d.attempts + 1
            vals = {"attempts": attempts, "status_code": code, "signature": signature, "last_error": error,
                    "duration_ms": int((time.monotonic() - started) * 1000) if code else 0}
            if 200 <= code < 300:
                vals.update(state="delivered", next_attempt_at=False)
            elif attempts >= hook.max_attempts:
                vals.update(state="failed", next_attempt_at=False)
            else:
                wait = BACKOFF_MINUTES[min(attempts - 1, len(BACKOFF_MINUTES) - 1)]
                vals.update(state="retrying", next_attempt_at=fields.Datetime.now() + timedelta(minutes=wait))
            d.write(vals)
