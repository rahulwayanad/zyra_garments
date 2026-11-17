# zyra_garment_cockpit — Cockpits

One cockpit per department (screens 1, 5–17, 20/21 present mode), all read-only, all served by one Odoo client
action (`zyra_garment_cockpit`) whose tabs switch cockpit. Compliance (18) and Made to Measure (19) are backlog.

## Data layer — `garment.cockpit` (AbstractModel, no table)
- `env["garment.cockpit"].get_cockpit(key, filters)` → `{key, title, subtitle, data_date, cockpits, filters,
  headline, tiles, panels}`.
  - headline: list of parts, each a plain string or `{t, tone: b|bad|warn}` (bold / red / amber).
  - tile: `{key, label, value, state: good|warn|bad|"", fmt: int|pct|money|float|text, display?, note?, model,
    domain}` — `display` is the text shown (money as ₹4.82 L / $242.4k); the client opens `model` filtered by
    `domain` when the tile is clicked.
  - panel (drawn in order, two per row):
    - `chart`: `{kind: bar|line, labels, series: [{label, values, color}], stacked, value_labels, ref, legend}`
      (`ref` = dashed limit line, e.g. DHU limit, margin floor);
    - `donut`: `{segments: [{label, value, color}], total}`;
    - `hbars`: `{rows: [{label, value, text, tone, width}]}` (ranked horizontal bars);
    - `table`: `{model, columns: [{label, align}], rows: [{id, tone, cells}]}` — a cell is text,
      `{pct, tone}` (progress bar) or `{badge, tone}`; a row with an id opens that record.
- `get_cockpit_list()` → `[{key, title}]`.
- Keys and methods (`_cockpit_<key>`): `pulse` (5), `orders` (6), `costing` (7), `samples` (8), `tna` (9),
  `fabric` (10), `cutting` (11), `sewing` (1), `capacity` (12), `jobwork` (13), `quality` (14), `shipping` (15),
  `wages` (16), `profit` (17).
- Aggregates use `_read_group` / `search_count` (`_sum`, `_by` helpers). A non-stored field is summed in Python
  over one search (no per-record queries).
- Reuses: `garment.line._garment_hourly_board()` / `_garment_daily_summary()` (sewing),
  `garment.order.pnl._garment_profit_summary(domain)` (profit).

## Menus
- Garment › **Cockpits** (`action_garment_cockpit`, opens Factory Pulse; tabs for the others).
- Garment › Sewing Floor › **Sewing Floor Cockpit** (`action_garment_cockpit_sewing`).

## Present mode (21)
"Present" button: full screen (browser Fullscreen API), auto-refresh every 60 s.

## Decisions
- Open order = state confirmed / in production / packed; late = open and ex-factory date before today.
- Filters (`{days, buyer_id, business_model}`) apply to every cockpit: buyer and business model through the
  record's own `buyer_id` or its production order; the period drives the time charts.
- Output today and the sewing floor come from each line's hourly board (one call per line; a factory has few
  lines) so the cockpit shows exactly what the line TV shows.
- DHU = defects ÷ pieces checked of inline inspections × 100; the limit is the company's DHU limit (quality).
  Tile tone: red above the limit, amber from 80 % of it.
- Failed final = final inspection with result `failed`. Finals blocking = open orders whose final inspection failed.
- Pieces to pack = Σ max(ordered − packed, 0) per order: an over-packed order does not offset another.
- Costing: approved sheets of the last 12 months; floor = company margin floor.
- Samples late / approval cards overdue use the merch module's `is_overdue`. Orders without PP sample = open
  orders whose `pp_sample_ok` is false.
- Time & action: open = no actual date; on-time share = on-time ÷ done in the month.
- Fabric: rolls on hand = lots with a roll status; "to inspect" = received rolls with no inspection yet,
  "received" = received rolls being inspected.
- Fabric utilisation = Σ(marker efficiency × marker length × plies) ÷ Σ fabric laid, over cut lays: the share of
  laid fabric that ends up in pieces (always ≤ marker efficiency). The design's sample numbers (utilisation above
  marker efficiency) came from a consumption-based figure; on the demo data that exceeds 100 %, so it was not used.
- Capacity: next 8 weeks from this Monday; a plan's minutes are spread evenly over its working days
  (6-day week); capacity = Σ line `capacity_minutes` per day × 6 × 8.
- Wages: "this week" = the latest wage-sheet period; gross = piece earnings + top-up + incentive + overtime;
  cost per standard minute = gross ÷ minutes earned. Wages by week shown in lakh (₹) or thousands.
- Profit: closed orders with ex-factory in the period, at least the last 90 days.
- Money: ₹ shown Indian style (₹4.82 L short, ₹4,82,310 full); other currencies $242.4k / $9,140.
- No demo data of its own: the cockpits read the department modules' demo data.

## Server note — time zones
Chrome reports India as `Asia/Calcutta`, and Odoo stores the browser's zone on a user's first login. PostgreSQL
on Ubuntu 26.04 only knows that alias when the `tzdata-legacy` package is installed; without it every
grouped-by-day read (cockpit charts, and standard Odoo graph/pivot views) fails with
`time zone "Asia/Calcutta" not recognized`. Install `tzdata-legacy` on the server (or set users to
`Asia/Kolkata`).

## Not done yet
- Day/Night shift button only toggles the label; scans are not split by shift yet (needs a shift definition).
- Compliance (18) and Made to Measure (19) tabs: backlog, not shown.
