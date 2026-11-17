import json

from odoo import http
from odoo.http import request

from ..models.garment_api_key import API_RESOURCES, API_SCOPES


class GarmentApi(http.Controller):

    def _token(self):
        auth = request.httprequest.headers.get("Authorization", "")
        return auth[7:].strip() if auth.lower().startswith("bearer ") else None

    def _reply(self, status, result):
        return request.make_response(json.dumps(result, default=str), status=status,
                                     headers=[("Content-Type", "application/json")])

    def _call(self, resource, record_id=None):
        method = request.httprequest.method
        body = None
        if method == "POST":
            try:
                body = json.loads(request.httprequest.get_data() or b"{}")
            except ValueError:
                return self._reply(400, {"error": "bad_json", "message": "The body is not valid JSON."})
            if not isinstance(body, dict):
                return self._reply(400, {"error": "bad_json", "message": "Send one JSON object."})
        status, result = request.env["garment.api.key"].sudo()._garment_api_call(
            self._token(), method, resource, record_id=record_id, body=body,
            ip=request.httprequest.remote_addr, params=dict(request.httprequest.args))
        return self._reply(status, result)

    @http.route("/api/garment/v1/<string:resource>", type="http", auth="none", methods=["GET", "POST"],
                csrf=False, save_session=False)
    def collection(self, resource, **kw):
        return self._call(resource)

    @http.route("/api/garment/v1/<string:resource>/<int:record_id>", type="http", auth="none",
                methods=["GET"], csrf=False, save_session=False)
    def record(self, resource, record_id, **kw):
        return self._call(resource, record_id)

    @http.route("/api/garment/v1", type="http", auth="user", methods=["GET"])
    def reference(self, **kw):
        """In-app API reference (screen 120)."""
        return request.render("zyra_garment_connect.api_reference_page", {
            "resources": [(r, API_RESOURCES[r][0], API_RESOURCES[r][1]) for r in API_SCOPES],
            "base_url": request.httprequest.host_url.rstrip("/") + "/api/garment/v1",
        })
