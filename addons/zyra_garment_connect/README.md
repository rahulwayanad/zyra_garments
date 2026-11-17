# zyra_garment_connect

API, webhooks and CSV imports for the Zyra garment ERP (Odoo 18 CE). Depends: `zyra_garment_base`,
`zyra_garment_merch`, `zyra_garment_theme`, `hr`. Other modules are read softly (`if 'garment.x' in env`).
Screens: 20 (cockpit), 114 (API key), 115 (webhook), 118 (import job), 120 (API reference), 121 (First Steps).

## Models
- `garment.api.key` (`KEY/YYYY/NNNN`): `read_scopes` / `post_scopes` (comma lists of orders, bundles, scans, rolls,
  cartons, styles, rosters), `rate_limit` (calls/min), `expiry_date`, `allowed_ips` (addresses/CIDR), `user_id`
  (API runs with this user's rights), `company_id`, state active/revoked. Only the SHA-256 of the secret is stored
  (`key_hash`, `key_prefix`); **Rotate** shows the new secret once. KPIs: calls 30 d, refused, expires in.
- `garment.api.call`: call log (method, path, status, ms, IP, error).
- `garment.webhook` (`WH/YYYY/NNNN`): url, `events`, secret, `max_attempts` (5), state active/paused.
  `garment.webhook.delivery`: one per event × hook; pending → delivered / retrying → failed.
- `garment.import` (`IMP/YYYY/NNNN`) + `garment.import.line`: CSV for rolls / rosters / orders.
  Uploaded → **Dry Run** (every row is created/written inside a savepoint and rolled back; each row gets
  Create / Update / Skip + note) → Checked → **Apply** (writes only rows not marked Skip) → Applied.
- `garment.connect.cockpit`, `garment.first.steps`: transient, compute-only screens.

## API (`/api/garment/v1`)
Bearer key. `GET /<resource>` (limit/offset), `GET /<resource>/<id>`, `POST /scans|rolls|rosters|orders`.
Codes: 200/201, 400 bad JSON, 401 key missing/revoked/expired, 403 scope/IP/access, 404, 405, 422 business rule,
429 rate limit. `GET /api/garment/v1` (logged-in user) = reference page. Core logic:
`env['garment.api.key']._garment_api_call(token, method, resource, record_id, body, ip, params)` → `(status, dict)`.

## Webhooks — what other modules can rely on
```python
if 'garment.webhook' in env:
    env['garment.webhook'].sudo()._garment_emit('bundle.cut', {...}, company=rec.company_id)
```
Events: order.confirmed, order.shipped (emitted here from `garment.order` state changes), bundle.cut,
bundle.scanned (emitted by POST /scans), final.failed, shipment.left. Body is JSON; header
`X-Zyra-Signature: sha256=<hex HMAC-SHA256(secret, raw body)>`. Cron "Garment: deliver webhooks" (every minute)
sends due deliveries; back-off 1, 5, 15, 60 min.

## Menus
Garment › Connect (Factory Manager; write access admin): Cockpit, First Steps, API Keys, Webhooks, Import Jobs,
API Call Log, API Reference.

## Decisions
- Scopes are comma lists per resource, validated (simpler than a scope model; screen shows them as text).
- Rate limit = calls in the last 60 s (429s not counted) ≥ limit → 429.
- Import "Update" = same roll no. + fabric (rolls) or same employee name (rosters); orders always create.
- Portal views / documents to review on the cockpit show 0 until portal / document reading exist.

## Not done yet
- bundle.cut / final.failed / shipment.left are not emitted yet: cutting, quality and shipping must call
  `_garment_emit` (request to write in docs/requests).
- Cockpit line chart "calls per day by key"; screen 118 row columns (roll, fabric, length, dye lot) are shown as one
  "Values" column; `length` column for rolls not imported.
- Optional AI document reading (116–117) not built. No HttpCase test of the controller (logic tested directly).
