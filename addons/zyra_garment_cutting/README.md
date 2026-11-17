# zyra_garment_cutting

Cutting room for the Zyra garment ERP (Odoo 18 CE): **markers**, **cut plans** with a lay builder,
**lays** spread on approved fabric rolls, **bundles** and the printed **bundle ticket** with one tear-off QR
coupon per sewing operation.

- Depends: `zyra_garment_base`, `zyra_garment_theme`, `zyra_garment_merch`, `stock`
- Version `18.0.1.0.0`, licence OPL-1. Screens: 46–53.

## Coupon payload — the contract for zyra_garment_sewing (T9)

Every coupon QR holds plain text:

```
ZG1|<bundle id>|<operation line id>|<check>
```

| Part | Meaning |
|---|---|
| `ZG1` | format version |
| `<bundle id>` | `garment.bundle` database id |
| `<operation line id>` | `zyra.techpack.operation` id (the tech pack operation line of the coupon) |
| `<check>` | 6 upper-case hex chars: first 6 of HMAC-SHA256 of `ZG1|<bundle id>|<operation line id>` keyed with the `database.secret` system parameter |

API (all on `garment.bundle`, model methods):

```python
bundle, operation = env["garment.bundle"]._garment_parse_coupon(payload)   # raises UserError with an operator sentence
coupon = env["garment.bundle"]._garment_coupon_from_payload(payload)       # garment.bundle.coupon
done = coupon._garment_record_scan(employee=None, pieces=None, rejected=0, scanned_at=None, reason=None)
```

`_garment_record_scan` refuses a second scan (naming who scanned it), moves the bundle to `in_sewing` on the
first scan and to `sewn` when every coupon is scanned, and returns `True` when this scan completed the bundle.
Posting `sewn` progress on the order is left to the caller (sewing).

## Models

- `garment.marker` / `garment.marker.line` — marker of a style: size ratio, length (m), efficiency %.
  CSV import wizard `garment.marker.import`.
- `garment.cut.plan` (`CP/…`) — one per production order and colourway (one open plan at a time). Size lines
  `garment.cut.plan.size`: ordered, to cut (= ordered + extra cut %, rounded up), planned, planned %. Fabric
  from the tech pack fabric line of the colourway; required fabric = consumption with wastage.
  States draft → approved → cutting → done / cancel.
- `garment.cut.plan.proposal` — proposed lay (marker × plies); fabric = plies × (marker length + end
  allowance). Approving the plan turns each proposal into a lay.
- `garment.cut.plan.builder` (wizard, screen 48) — greedy proposal from the markers covering what is left per
  size; plies editable before approval; re-propose only what is left after existing lays.
- `garment.lay` (`LAY/…`) — marker, plies planned/spread, lay length, end allowance, fabric laid =
  plies × (length + end allowance), end loss %, rolls (`garment.lay.roll`: `stock.lot`, plies, ply numbers run
  on from roll to roll, shade), table, spreader, cutter. Mixed shades are flagged.
  States planned → spread → cut → bundled / cancel. **Cut** checks rolls (approved only, plan's fabric, enough
  metres), consumes fabric (one done stock move per roll to production) and calls
  `order._garment_add_progress('cut', colour, size, plies × ratio, ref=lay)`.
- `garment.bundle` (`BND/…`) — order, colourway, size, lay, plies (from–to), roll, shade, pieces, line, stage
  cut / issued / in_sewing / sewn / finished; kanban by stage (screens 50–52); issue and split wizards.
- `garment.bundle.coupon` — one per tech pack operation of the bundle, with scan data.
- `garment.order` (inherited) — "Propose cut plan" (one plan per colourway) and bundle count.

## Guard rails against typing errors (added 17 Nov 2026, after a lay of 1,000 plies × 1,000 m)

| Rule | When |
|---|---|
| A marker is at most **4 m per piece** (length ÷ pieces per ply; `MAX_METRES_PER_PIECE`) | saving a marker |
| A marker needs its **width** and **efficiency** before it is used (CSV import may still bring length only; a re-import without those columns keeps the values) | approving a cut plan, spreading or cutting a lay |
| **Lay length = marker length**, within 5 % (at least 10 cm). It is filled from the marker; end allowance is separate | saving a lay |
| **Planned plies ≤ the plan's maximum plies**, and **plies on the rolls ≤ planned plies** | saving a lay |
| Rolls approved, of the plan's fabric and with **enough metres** — now checked at **Start Spreading** as well as at Confirm Cut | spreading, cutting |

## Report

`Bundle ticket` (screen 53): header + one tear-off QR coupon per operation. QR via Odoo's report barcode, with
an SVG fallback when the server's reportlab has no PNG renderer.

## Tests (`tests/`) — 53, all green

Cut plan (lay proposal covers sizes exactly, max plies, no overcut, builder), lay (fabric formula, roll
rules, cut progress, fabric consumption, rights), bundle (split by plies/roll/bundle size, coupons per
operation, payload round trip and tampering, scan once, stage moves, ticket report).

## Decisions

- Coupon payload uses database ids plus an HMAC check rather than names, so it is short (small QR) and cannot be
  forged by retyping a bundle number.
- Lay proposal is greedy (most pieces per lay, ties to better efficiency) and never overcuts; exact coverage
  relies on single-size markers being present, which the demo and import provide.
- Fabric is consumed when the lay is cut (not when spread), one stock move per roll.
- Bundles never mix rolls, so a bundle always has one shade.

## Not done yet

- Nothing known beyond the screens' optional extras.
