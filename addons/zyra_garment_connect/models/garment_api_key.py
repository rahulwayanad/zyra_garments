import hashlib
import ipaddress
import secrets
import time
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

# resource -> (model, fields read through the API, extra domain)
API_RESOURCES = {
    "orders": ("garment.order", ["name", "state", "buyer_id", "buyer_po", "style_id", "date_order",
                                 "ex_factory_date", "qty_ordered"], []),
    "bundles": ("garment.bundle", ["name", "order_id", "colour_id", "size_id", "ply_from", "ply_to", "pieces",
                                   "stage", "line_id", "shade"], []),
    "scans": ("garment.bundle.coupon", ["bundle_id", "operation_id", "state", "employee_id", "pieces",
                                        "rejected", "scanned_at"], []),
    "rolls": ("stock.lot", ["name", "product_id", "roll_status", "dye_lot", "shade_group", "shrinkage_group",
                            "width_cm", "gsm"], [("is_fabric_roll", "=", True)]),
    "cartons": ("garment.carton", ["name", "state", "order_id", "pieces", "net_weight", "gross_weight", "sscc"],
                []),
    "styles": ("garment.style", ["name", "code", "buyer_id", "season_id"], []),
    "rosters": ("hr.employee", ["name", "job_title", "department_id"], []),
}
API_SCOPES = sorted(API_RESOURCES)
API_PAGE_SIZE = 80


def _hash_token(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def _split(scopes):
    return [s.strip() for s in (scopes or "").split(",") if s.strip()]


class GarmentApiKey(models.Model):
    _name = "garment.api.key"
    _description = "Garment API Key"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Key", required=True, tracking=True, help="What this key is for.")
    reference = fields.Char(string="Reference", default="/", readonly=True, copy=False)
    state = fields.Selection([("active", "Active"), ("revoked", "Revoked")], default="active", required=True,
                             tracking=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one("res.users", string="Runs As", required=True, default=lambda self: self.env.user,
                              help="The API works with this user's access rights.")
    key_prefix = fields.Char(string="Key Starts With", readonly=True, copy=False)
    key_hash = fields.Char(readonly=True, copy=False, groups="base.group_system")
    read_scopes = fields.Char(string="Read", help="Comma-separated: " + ", ".join(API_SCOPES))
    post_scopes = fields.Char(string="Post", help="Comma-separated: " + ", ".join(API_SCOPES))
    rate_limit = fields.Integer(string="Rate Limit (calls / min)", default=120, required=True)
    expiry_date = fields.Date(string="Expires")
    allowed_ips = fields.Char(string="Allowed IPs", help="Comma-separated addresses or networks. Empty = any.")
    call_ids = fields.One2many("garment.api.call", "key_id", string="Call Log")
    calls_30d = fields.Integer(string="Calls, 30 Days", compute="_compute_kpis")
    refused_30d = fields.Integer(string="Refused", compute="_compute_kpis")
    expires_in_days = fields.Integer(string="Expires In (days)", compute="_compute_kpis")
    rate_limit_label = fields.Char(compute="_compute_kpis")
    allowed_ips_label = fields.Char(compute="_compute_kpis")

    @api.constrains("read_scopes", "post_scopes")
    def _check_scopes(self):
        for key in self:
            bad = [s for s in _split(key.read_scopes) + _split(key.post_scopes) if s not in API_RESOURCES]
            if bad:
                raise ValidationError(_("Unknown API scope(s): %(bad)s. Use: %(ok)s",
                                        bad=", ".join(bad), ok=", ".join(API_SCOPES)))

    @api.constrains("rate_limit")
    def _check_rate_limit(self):
        if any(k.rate_limit <= 0 for k in self):
            raise ValidationError(_("The rate limit must be at least one call per minute."))

    def _compute_kpis(self):
        since = fields.Datetime.now() - timedelta(days=30)
        today = fields.Date.context_today(self)
        Call = self.env["garment.api.call"].sudo()
        for key in self:
            calls = Call.search([("key_id", "=", key.id), ("create_date", ">=", since)]) if key.id else Call
            key.calls_30d = len(calls)
            key.refused_30d = len(calls.filtered(lambda c: c.status >= 400))
            key.expires_in_days = (key.expiry_date - today).days if key.expiry_date else 0
            key.rate_limit_label = _("%s / min", key.rate_limit)
            key.allowed_ips_label = key.allowed_ips or _("Any")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", "/") == "/":
                vals["reference"] = self.env["ir.sequence"].next_by_code("garment.api.key") or "/"
        return super().create(vals_list)

    # ---------------------------------------------------------------- tokens
    def _garment_new_token(self):
        """Give the key a new secret. Returns the token in clear; only its SHA-256 is stored."""
        self.ensure_one()
        token = "zg_" + secrets.token_urlsafe(32)
        self.sudo().write({"key_hash": _hash_token(token), "key_prefix": token[:10]})
        return token

    def action_rotate(self):
        self.ensure_one()
        token = self._garment_new_token()
        self.message_post(body=_("Key rotated; the old secret no longer works."))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("New API key — copy it now, it is shown only once"), "message": token,
                       "sticky": True, "type": "warning"},
        }

    def action_revoke(self):
        self.write({"state": "revoked"})

    def action_activate(self):
        self.write({"state": "active"})

    # ---------------------------------------------------------------- checks
    def _garment_ip_allowed(self, ip):
        self.ensure_one()
        nets = _split(self.allowed_ips)
        if not nets or nets == ["*"]:
            return True
        try:
            addr = ipaddress.ip_address(ip or "")
        except ValueError:
            return False
        for net in nets:
            try:
                if addr in ipaddress.ip_network(net, strict=False):
                    return True
            except ValueError:
                continue
        return False

    def _garment_rate_exceeded(self):
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(seconds=60)
        used = self.env["garment.api.call"].sudo().search_count([
            ("key_id", "=", self.id), ("create_date", ">=", since), ("status", "!=", 429)])
        return used >= self.rate_limit

    def _garment_has_scope(self, method, resource):
        self.ensure_one()
        scopes = _split(self.post_scopes if method == "POST" else self.read_scopes)
        return resource in scopes

    # ---------------------------------------------------------------- the API
    @api.model
    def _garment_api_call(self, token, method, resource, record_id=None, body=None, ip=None, params=None):
        """Run one API call. Returns ``(http_status, json_dict)`` and logs the call.

        Used by the HTTP controller and by tests (no HTTP needed)."""
        started = time.monotonic()
        key = self.sudo().search([("key_hash", "=", _hash_token(token))], limit=1) if token else self.browse()
        status, result = self._garment_api_dispatch(key, method, resource, record_id, body, ip, params or {})
        self.env["garment.api.call"].sudo().create({
            "key_id": key.id or False, "method": method, "path": "/api/garment/v1/%s%s" % (
                resource, "/%s" % record_id if record_id else ""),
            "status": status, "ip": ip, "duration_ms": int((time.monotonic() - started) * 1000),
            "error": result.get("error") if status >= 400 else False,
        })
        return status, result

    def _garment_api_dispatch(self, key, method, resource, record_id, body, ip, params):
        if not key:
            return 401, {"error": "invalid_key", "message": "Missing or unknown API key."}
        if key.state != "active":
            return 401, {"error": "revoked", "message": "This API key was revoked."}
        if key.expiry_date and key.expiry_date < fields.Date.context_today(key):
            return 401, {"error": "expired", "message": "This API key expired on %s." % key.expiry_date}
        if not key._garment_ip_allowed(ip):
            return 403, {"error": "ip_not_allowed", "message": "Calls from %s are not allowed." % ip}
        if key._garment_rate_exceeded():
            return 429, {"error": "rate_limited",
                         "message": "Rate limit of %s calls per minute reached." % key.rate_limit}
        if resource not in API_RESOURCES or API_RESOURCES[resource][0] not in self.env:
            return 404, {"error": "unknown_resource", "message": "No resource '%s'." % resource}
        if method not in ("GET", "POST"):
            return 405, {"error": "method_not_allowed", "message": "Use GET or POST."}
        if not key._garment_has_scope(method, resource):
            return 403, {"error": "scope", "message": "This key has no %s scope for '%s'." % (
                "post" if method == "POST" else "read", resource)}
        env = self.env(user=key.user_id.id, context=dict(self.env.context, allowed_company_ids=[
            key.company_id.id]), su=False)
        try:
            with self.env.cr.savepoint():
                if method == "GET":
                    return self._garment_api_get(env, resource, record_id, params)
                return self._garment_api_post(env, resource, body or {})
        except AccessError as e:
            return 403, {"error": "access", "message": str(e)}
        except (UserError, ValidationError) as e:
            return 422, {"error": "invalid", "message": str(e.args[0] if e.args else e)}
        except (ValueError, TypeError, KeyError) as e:
            return 400, {"error": "bad_request", "message": str(e)}

    def _garment_api_get(self, env, resource, record_id, params):
        model_name, _flds, domain = API_RESOURCES[resource]
        Model = env[model_name]
        names = ["id"] + [f for f in _flds if f in Model._fields]
        if record_id:
            rec = Model.search(domain + [("id", "=", int(record_id))], limit=1)
            if not rec:
                return 404, {"error": "not_found", "message": "No %s with id %s." % (resource, record_id)}
            return 200, {"data": _jsonable(rec.read(names)[0])}
        limit = min(int(params.get("limit") or API_PAGE_SIZE), 500)
        offset = int(params.get("offset") or 0)
        rows = Model.search_read(domain, names, limit=limit, offset=offset, order="id")
        return 200, {"data": [_jsonable(r) for r in rows], "count": Model.search_count(domain),
                     "limit": limit, "offset": offset}

    def _garment_api_post(self, env, resource, body):
        if resource == "scans":
            payload = body.get("payload")
            if not payload:
                raise ValueError("Send the coupon QR text in 'payload'.")
            coupon = env["garment.bundle"]._garment_coupon_from_payload(payload)
            employee = env["hr.employee"].browse(int(body["employee_id"])) if body.get("employee_id") else None
            done = coupon._garment_record_scan(employee=employee, pieces=body.get("pieces"),
                                               rejected=int(body.get("rejected") or 0))
            if "garment.webhook" in env:
                env["garment.webhook"].sudo()._garment_emit("bundle.scanned", {
                    "bundle": coupon.bundle_id.name, "bundle_id": coupon.bundle_id.id, "completed": bool(done)})
            return 201, {"data": {"coupon_id": coupon.id, "bundle_completed": bool(done)}}
        vals_fn = {
            "rolls": env["garment.import"]._garment_vals_rolls,
            "rosters": env["garment.import"]._garment_vals_rosters,
            "orders": env["garment.import"]._garment_vals_orders,
        }.get(resource)
        if not vals_fn:
            return 405, {"error": "method_not_allowed", "message": "'%s' is read-only." % resource}
        model_name = API_RESOURCES[resource][0]
        rec = env[model_name].create(vals_fn({k: str(v) for k, v in body.items() if v is not None}))
        return 201, {"data": {"id": rec.id, "name": rec.display_name}}


def _jsonable(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, tuple) and len(v) == 2:
            v = {"id": v[0], "name": v[1]}
        elif hasattr(v, "isoformat"):
            v = v.isoformat()
        out[k] = v
    return out


class GarmentApiCall(models.Model):
    _name = "garment.api.call"
    _description = "Garment API Call Log"
    _order = "id desc"

    key_id = fields.Many2one("garment.api.key", string="API Key", index=True, ondelete="cascade")
    company_id = fields.Many2one(related="key_id.company_id", store=True)
    method = fields.Char(required=True)
    path = fields.Char(required=True)
    status = fields.Integer(required=True, index=True)
    ip = fields.Char(string="IP")
    duration_ms = fields.Integer(string="Time (ms)")
    error = fields.Char()
    create_date = fields.Datetime(string="Called At", index=True)
