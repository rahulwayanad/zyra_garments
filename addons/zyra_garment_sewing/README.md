# zyra_garment_sewing

Sewing floor for the Zyra garment ERP (Odoo 18 CE): **sewing lines**, **operation bulletins** per style,
a **line balancing** wizard, **coupon scans** with operator minutes and earnings, an **offline-safe batch replay**
for scan stations, and the figures behind the **line TV board** and **daily line summary**.

- Depends: `zyra_garment_base`, `zyra_garment_theme`, `zyra_garment_merch`, `zyra_garment_cutting`, `hr`, `mrp`
- Version `18.0.1.0.0`, licence OPL-1. Screens: 3, 4, 54–58 (see "Not done yet").

## Models

| Model | What |
|---|---|
| `garment.line` | Sewing line. `_inherits` `mrp.workcenter` (`workcenter_id`), so bundles / orders keep pointing at the work centre. Fields: `supervisor_id`, `employee_ids`, `operator_count`, `machine_count`, `working_minutes` (per day), `capacity_minutes` = operators × minutes, `target_efficiency`, `current_bulletin_id`, `target_per_hour` = operators × 60 × target eff. ÷ bulletin SAM. |
| `garment.bulletin` / `garment.bulletin.line` | Operation bulletin of a style (screen 54): operation, section, machine, SAM, target/hour (= 60 ÷ SAM), piece rate. "Load from Tech Pack" fills it from `zyra.techpack.operation` (piece rate = SAM × company minute rate). Totals: SAM, operations, labour per piece. |
| `garment.line.balancing` (wizard, screen 55) | Pitch time, target and balanced output, balance loss %, bottleneck, operators per station. "Apply to Line" sets the line's running bulletin and operators. |
| `garment.scan` | One coupon scan (screen 57): coupon, payload, operator, line, order, bundle, operation, pieces, rejected, SAM, minutes earned = pieces × SAM, minute rate, earnings = minutes × rate, `is_last_operation` (scan completed the bundle), `client_uuid` (device scan id). Unique per coupon and per device id. |

## API other modules / the scan station can rely on

```python
scan = env["garment.scan"]._garment_scan(payload, employee, line=None, client_uuid=None,
                                         scanned_at=None, rejected=0, reason=None)
# -> garment.scan; UserError with an operator sentence on bad coupon / duplicate coupon / no badge.
# Calls coupon._garment_record_scan (cutting contract); when the bundle completes, posts
# order._garment_add_progress('sewn', colour, size, good pieces, ref=bundle name).

results = env["garment.scan"].garment_sync_batch([{uuid, payload, employee_id, line_id, scanned_at, rejected}])
# -> [{uuid, status: 'ok'|'duplicate'|'error', message, scan_id}]  — idempotent on uuid (replay safe)

line._garment_daily_summary(day=None)  # pieces, earned/available/lost minutes, efficiency, WIP pieces/days, dhu, rejected
line._garment_hourly_board(day=None, first_hour=8, hours=9)  # hours[{hour, output, target, efficiency}], top operator
env["garment.line"]._garment_from_workcenter(workcenter)
env["garment.line.balancing"]._garment_balance(sams, operators)  # pure maths
```

## Formulas (garment-domain)

- Minutes earned = pieces × SAM; earnings = minutes × minute rate.
- Minute rate = bulletin piece rate ÷ SAM for the style's operation; else system parameter
  `zyra_garment_sewing.minute_rate`.
- Efficiency = earned minutes ÷ (operators × minutes per day) × 100; lost minutes = available − earned.
- Output = pieces of scans that completed a bundle (last operation). WIP days = pieces on the line ÷ day output.
- Balancing: pitch = total SAM ÷ operators; operators per station = ceil(SAM ÷ pitch), trimmed to the line's
  operators; cycle = SAM ÷ operators; bottleneck = longest cycle; balanced/h = 60 ÷ bottleneck cycle;
  target/h = operators × 60 ÷ total SAM; balance loss % = (1 − total SAM ÷ (operators × bottleneck cycle)) × 100.

## Demo

Four lines on merch's demo work centres, one bulletin per tech pack with operations, minute rate 1.8,
four cut bundles issued to Line 1 and scanned (three sewn, one in sewing).

## Menus

Garment › Sewing Floor › Coupon Scans, Operation Bulletins, Sewing Lines.

## Security

Line supervisor: lines, bulletins, scans (create), balancing. Wages: read scans. Factory manager: everything.
All users: read lines and bulletins. Scans are written with `sudo()` after the checks so a scan station user only
needs the line-supervisor role.

## Tests (`tests/test_sewing.py`)

Balancing maths (pitch, target, bottleneck, loss), balancing wizard on a bulletin, minutes/earnings rule,
duplicate coupon refused, last operation completes the bundle and posts sewn, offline batch replay idempotent,
daily summary efficiency rule + hourly board, scan without badge refused.

## Decisions

- `garment.line` is required by the kit, while merch/cutting decided sewing lines are `mrp.workcenter`: the line
  `_inherits` the work centre, so both hold. Scans find their line from `bundle.line_id` (a work centre).
- Earnings use a minute rate (piece rate ÷ SAM) so "earnings = minutes × rate" and "piece rate" agree.
- Offline idempotency is keyed on a device-generated `client_uuid`; a duplicate coupon with a new uuid is an
  error (reported back to the station), not a silent skip.
- 'sewn' progress posts the bundle's good pieces (pieces − worst rejected, cutting's `good_pieces`).
- DHU in the daily summary is filled only if a quality module provides `garment.inspection._garment_line_dhu`.

## Screens (segment 2)

- Scan station (screen 4): client action `zyra_garment_scan_station`; IndexedDB queue (`static/src/scan_station/offline_queue.js`) sent through `garment_sync_batch`; RPC `station_lines`, `station_badge`, `station_stats`.
- Line TV board (56): full-screen client action `zyra_garment_line_tv_board`, RPC `garment.line.garment_tv_board`, refresh every minute.
- Daily line summary (58): model `garment.line.day` (LD/…), with hours, downtime and open/closed states, plus an hourly cron.
- Planning board (3): model `garment.line.plan` and client action `zyra_garment_line_planning_board`, with drag to move a bar to another line or week. RPC `garment_board`, `garment_plan_orders`, `garment_move`.
- Bulletin (54): versions, draft/approved states, sewing SAM (all sections except preparation and finishing), rate card, manual rate.

- Line balancing (55): stored `garment.line.balancing` (LB/…), states draft → applied (+ cancelled), stations
  `garment.line.balancing.station` with operators needed (SAM ÷ pitch) and assigned in half operators, station
  efficiency, capacity/h = assigned × 60 ÷ SAM × eff; balanced output = lowest capacity (bottleneck);
  target/h = operators × 60 ÷ SAM × planned eff; loss % = (1 − balanced ÷ target) × 100 (matches the screen).
  The wizard is gone; "Balance Line" on a bulletin creates a record. Code stays in `wizard/line_balancing.py`.
- Line day (58): Defects tab (`garment.line.day.defect`) and the "Print Hourly Report" QWeb PDF.

## Not done yet

- DHU in the daily summary waits on quality.
- Client actions were checked only by syntax and the assets bundle compiling. Nobody has opened them in a browser yet.
- Times on scans and summaries use UTC day boundaries.
