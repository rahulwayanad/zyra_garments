import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

SEND = "odoo.addons.zyra_garment_connect.models.garment_webhook.requests.post"


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


@tagged("post_install", "-at_install")
class TestConnect(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Key = cls.env["garment.api.key"]
        cls.key = cls.Key.create({
            "name": "Test shop", "user_id": cls.env.ref("base.user_admin").id,
            "read_scopes": "orders, rosters", "post_scopes": "orders", "rate_limit": 100,
        })
        cls.token = cls.key._garment_new_token()
        # demo webhooks must not receive the test events
        cls.env["garment.webhook"].search([]).write({"state": "paused"})
        cls.dept = cls.env["hr.department"].create({"name": "Sewing Line 7 Test"})

    def call(self, method, resource, token=None, **kw):
        return self.Key._garment_api_call(token or self.token, method, resource, ip="10.0.0.5", **kw)

    # ---------------------------------------------------------------- keys and scopes
    def test_token_is_stored_only_as_hash(self):
        self.assertTrue(self.token.startswith("zg_"))
        self.assertEqual(self.key.sudo().key_hash, hashlib.sha256(self.token.encode()).hexdigest())
        self.assertEqual(self.key.key_prefix, self.token[:10])

    def test_unknown_or_missing_key_is_refused_401(self):
        self.assertEqual(self.call("GET", "orders", token="zg_wrong")[0], 401)
        self.assertEqual(self.Key._garment_api_call(None, "GET", "orders")[0], 401)

    def test_read_scope_allows_read(self):
        status, body = self.call("GET", "rosters")
        self.assertEqual(status, 200)
        self.assertIn("data", body)

    def test_scope_enforced_post_without_post_scope_is_403(self):
        employees = self.env["hr.employee"].search_count([])
        status, body = self.call("POST", "rosters", body={"name": "Anita Test"})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "scope")
        self.assertEqual(self.env["hr.employee"].search_count([]), employees, "a refused call writes nothing")

    def test_scope_enforced_read_without_read_scope_is_403(self):
        self.key.read_scopes = "orders"
        self.assertEqual(self.call("GET", "rosters")[0], 403)

    def test_post_with_post_scope_creates(self):
        self.key.post_scopes = "rosters"
        status, body = self.call("POST", "rosters", body={"name": "Meera Test", "department": self.dept.name})
        self.assertEqual(status, 201)
        emp = self.env["hr.employee"].browse(body["data"]["id"])
        self.assertEqual(emp.department_id, self.dept)

    def test_invalid_post_returns_422_and_writes_nothing(self):
        self.key.post_scopes = "rosters"
        status, _b = self.call("POST", "rosters", body={"name": "X", "department": "No such dept"})
        self.assertEqual(status, 422)

    def test_unknown_scope_name_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.key.read_scopes = "orders, payroll"

    def test_unknown_resource_404_and_record_404(self):
        self.assertEqual(self.call("GET", "payroll")[0], 404)
        self.assertEqual(self.call("GET", "rosters", record_id=99999999)[0], 404)

    def test_revoked_and_expired_keys_refused(self):
        self.key.action_revoke()
        self.assertEqual(self.call("GET", "rosters")[1]["error"], "revoked")
        self.key.action_activate()
        self.key.expiry_date = fields.Date.today() - timedelta(days=1)
        self.assertEqual(self.call("GET", "rosters")[1]["error"], "expired")

    def test_allowed_ips_enforced(self):
        self.key.allowed_ips = "192.168.1.0/24"
        self.assertEqual(self.call("GET", "rosters")[0], 403)
        self.key.allowed_ips = "10.0.0.0/8"
        self.assertEqual(self.call("GET", "rosters")[0], 200)

    def test_rate_limit_refuses_with_429_after_limit_per_minute(self):
        self.key.rate_limit = 3
        statuses = [self.call("GET", "rosters")[0] for _i in range(4)]
        self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(self.key.refused_30d, 1)
        self.assertEqual(self.key.calls_30d, 4)

    def test_every_call_is_logged(self):
        self.call("GET", "rosters")
        log = self.env["garment.api.call"].search([("key_id", "=", self.key.id)], limit=1)
        self.assertEqual((log.method, log.path, log.status, log.ip), ("GET", "/api/garment/v1/rosters", 200,
                                                                    "10.0.0.5"))

    # ---------------------------------------------------------------- webhooks
    def _hook(self, **vals):
        return self.env["garment.webhook"].create(dict({
            "name": "Buyer EDI test", "url": "https://edi.buyer.example/in",
            "events": "order.confirmed, order.shipped", "secret": "s3cret"}, **vals))

    def test_webhook_signature_is_hmac_sha256_of_body(self):
        hook = self._hook()
        delivery = self.env["garment.webhook"]._garment_emit("order.confirmed", {"order": "PO/1"})
        self.assertEqual(delivery.webhook_id, hook)
        with patch(SEND, return_value=FakeResponse(200)) as post:
            delivery._garment_send()
        sent_body = post.call_args.kwargs["data"]
        expected = hmac.new(b"s3cret", sent_body, hashlib.sha256).hexdigest()
        self.assertEqual(post.call_args.kwargs["headers"]["X-Zyra-Signature"], "sha256=" + expected)
        self.assertEqual(json.loads(sent_body)["data"]["order"], "PO/1")
        self.assertEqual(delivery.state, "delivered")

    def test_webhook_only_subscribed_active_hooks_get_event(self):
        self._hook()
        self._hook(name="paused", state="paused")
        self.assertFalse(self.env["garment.webhook"]._garment_emit("final.failed", {}))
        self.assertEqual(len(self.env["garment.webhook"]._garment_emit("order.shipped", {})), 1)

    def test_webhook_retries_with_backoff_then_fails(self):
        hook = self._hook(max_attempts=3)
        delivery = self.env["garment.webhook"]._garment_emit("order.confirmed", {})
        with patch(SEND, return_value=FakeResponse(503)):
            delivery._garment_send()
            self.assertEqual((delivery.state, delivery.attempts), ("retrying", 1))
            self.assertGreater(delivery.next_attempt_at, fields.Datetime.now())
            self.assertEqual(delivery.result_label, "Retrying (1 of 3)")
            delivery._garment_send()
            delivery._garment_send()
        self.assertEqual(delivery.state, "failed")
        self.assertEqual(hook.failures_30d, 1)

    def test_webhook_cron_sends_due_deliveries(self):
        self._hook()
        delivery = self.env["garment.webhook"]._garment_emit("order.confirmed", {})
        with patch(SEND, return_value=FakeResponse(204)):
            self.env["garment.webhook"]._cron_deliver()
        self.assertEqual(delivery.state, "delivered")

    def test_unknown_event_rejected(self):
        with self.assertRaises(ValidationError):
            self._hook(events="order.exploded")

    # ---------------------------------------------------------------- CSV import
    def _import(self, csv_text, target="rosters"):
        return self.env["garment.import"].create({
            "target": target, "filename": "x.csv", "file": base64.b64encode(csv_text.encode())})

    def test_dry_run_writes_nothing(self):
        before = self.env["hr.employee"].search_count([])
        imp = self._import("name,job_title,department\nRekha Dry,Operator,%s\nSuma Dry,Helper,\n" % self.dept.name)
        imp.action_dry_run()
        self.assertEqual(self.env["hr.employee"].search_count([]), before, "dry run must not create records")
        self.assertFalse(self.env["hr.employee"].search([("name", "in", ["Rekha Dry", "Suma Dry"])]))
        self.assertEqual((imp.state, imp.row_count, imp.create_count, imp.error_count), ("checked", 2, 2, 0))

    def test_dry_run_reports_each_bad_row(self):
        imp = self._import("name,department\nGood Row,%s\n,%s\nBad Dept,Nowhere\n" % (self.dept.name, self.dept.name))
        imp.action_dry_run()
        self.assertEqual(imp.line_ids.mapped("status"), ["create", "skip", "skip"])
        self.assertEqual(imp.line_ids.mapped("row_no"), [2, 3, 4])
        imp.action_apply()
        self.assertEqual(imp.line_ids.mapped("status"), ["created", "skip", "skip"],
                         "apply writes only the rows the dry run accepted")
        self.assertFalse(self.env["hr.employee"].search([("name", "=", "Bad Dept")]))

    def test_import_requires_dry_run_then_creates(self):
        imp = self._import("name,job_title\nLatha Real,Checker\n")
        with self.assertRaises(UserError):
            imp.action_apply()
        imp.action_dry_run()
        imp.action_apply()
        self.assertEqual(imp.state, "done")
        self.assertEqual(imp.created_count, 1)
        self.assertTrue(self.env["hr.employee"].search([("name", "=", "Latha Real")]))

    def test_roll_import_dry_run_writes_no_lot(self):
        product = self.env["product.product"].create({"name": "Jersey Test Fabric", "default_code": "JTF"})
        lots = self.env["stock.lot"].search_count([])
        imp = self._import("roll,product,dye_lot,gsm\nR-T-001,JTF,DL9,180\nR-T-002,NOPE,DL9,abc\n", "rolls")
        imp.action_dry_run()
        self.assertEqual(imp.line_ids.mapped("status"), ["create", "skip"])
        self.assertEqual(self.env["stock.lot"].search_count([]), lots)

    def test_existing_roll_is_updated_not_duplicated(self):
        product = self.env["product.product"].create({"name": "Twill Test Fabric", "default_code": "TTF"})
        lot = self.env["stock.lot"].create({"name": "R-U-1", "product_id": product.id, "is_fabric_roll": True,
                                            "dye_lot": "OLD"})
        imp = self._import("roll,product,dye_lot\nR-U-1,TTF,NEW\n", "rolls")
        imp.action_dry_run()
        self.assertEqual(imp.line_ids.status, "update")
        self.assertEqual(lot.dye_lot, "OLD", "dry run does not change the existing roll")
        imp.action_apply()
        self.assertEqual(lot.dye_lot, "NEW")
        self.assertEqual(self.env["stock.lot"].search_count([("name", "=", "R-U-1")]), 1)

    # ---------------------------------------------------------------- cockpit and first steps
    def test_cockpit_counts_calls_refusals_and_retries(self):
        self.call("GET", "rosters")
        self.call("GET", "payroll")
        cockpit = self.env["garment.connect.cockpit"].create({})
        self.assertGreaterEqual(cockpit.api_calls_30d, 2)
        self.assertGreaterEqual(cockpit.refused_30d, 1)
        self.assertIn("calls in 30 days", cockpit.headline)

    def test_first_steps_lists_nine_steps(self):
        steps = self.env["garment.first.steps"].create({})
        self.assertEqual(steps.steps_total, 9)
        self.assertIn("Scan the first coupon", steps.steps_html)

    def test_order_confirmation_queues_webhook(self):
        self._hook()
        order = self.env["garment.order"].search([("state", "=", "draft")], limit=1)
        if not order:
            self.skipTest("no draft demo order")
        order.write({"state": "confirmed"})
        delivery = self.env["garment.webhook.delivery"].search([("event", "=", "order.confirmed")], limit=1)
        self.assertIn(order.name, delivery.payload)
