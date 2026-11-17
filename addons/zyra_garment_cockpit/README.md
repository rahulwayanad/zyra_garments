# zyra_garment_cockpit — Cockpits

One cockpit per department (screens 1, 5–17, 20/21 present mode), all read-only, all served by one Odoo client
action (`zyra_garment_cockpit`) whose tabs switch cockpit. Compliance (18) and Made to Measure (19) are backlog.

## Data layer — `garment.cockpit` (AbstractModel, no table)
- `env["garment.cockpit"].get_cockpit(key)` → `{key, title, data_date, cockpits, headline?, tiles, charts, lists}`.
  - tile: `{key, label, value, state: good|warn|bad|"", fmt: int|pct|money|float|text, model, domain}` — the
    client opens `model` filtered by `domain` when the tile is clicked.
  - chart: `{key, title, type: bar|line, labels, values}`; list: `{key, title, columns, rows, model?}`.
- `get_cockpit_list()` → `[{key, title}]`.
- Keys and methods (`_cockpit_<key>`): `pulse` (5), `orders` (6), `costing` (7), `samples` (8), `tna` (9),
  `fabric` (10), `cutting` (11), `sewing` (1), `capacity` (12), `jobwork` (13), `quality` (14), `shipping` (15),
  `wages` (16), `profit` (17).
- Aggregates use `_read_group` / `search_count` (`_sum`, `_by` helpers). A non-stored field is summed in Python
  over one search (no per-record queries).
- Reuses: `garment.line._garment_hourly_board()` (sewing), `garment.order.pnl._garment_profit_summary()` (profit).

## Menus
- Garment › **Cockpits** (`action_garment_cockpit`, opens Factory Pulse; tabs for the others).
- Garment › Sewing Floor › **Sewing Floor Cockpit** (`action_garment_cockpit_sewing`).

## Present mode (21)
"Present" button: full screen (browser Fullscreen API), auto-refresh every 60 s.

## Decisions
- Open order = state confirmed / in production / packed; late = open and ex-factory date before today.
- Output today and the sewing floor come from each line's hourly board (one call per line; a factory has few
  lines) so the cockpit shows exactly what the line TV shows.
- DHU today = defects ÷ pieces checked of today's inline inspections × 100.
- Cartons waiting = cartons packed, not yet shipped. Failed finals = final inspections with result fail.
- Filters (`get_cockpit(key, {days, buyer_id, business_model})`): period 7/30/90/365 days drives the day charts;
  buyer and business model filter the open-order domain.
- Lines stopped today = lines with a downtime row on today's line day (`garment.line.day.downtime`); "stopped now"
  = those whose line day is still open; machines down = downtime rows with a machine. "Since" = time the downtime
  was logged (the sewing module stores no start time). On-standard % = average planned efficiency of line days.
- No demo data of its own: the cockpits read the department modules' demo data.

## Not done yet
- Per-screen layouts of 6–17 beyond tiles + generic charts/lists (they share one generic layout).
- Day shift button only toggles the label (Day / Night); scans are not split by shift yet.
- Buyer / business-model filters apply to order-based tiles of Factory Pulse only.
- Department readings: cutting shows fabric laid instead of fabric utilisation %.
- Browser check of the client action (no time in this segment).
