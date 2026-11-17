# zyra_garment_wages

Operator wages for the Zyra garment ERP (Odoo 18 CE). Depends: `zyra_garment_sewing`, `hr`, `account`.

## Models
| Model | Purpose |
|---|---|
| `garment.rate.card` | Minute value, hourly earnings at 100 % (= minute value × 60), hours/day, statutory minimum per day, overtime multiplier, incentive threshold (efficiency %) and incentive %, bulletins it prices (screen 80). |
| `garment.wage.sheet` (WS/YYYY/nnnn) | Weekly sheet per sewing line (empty line = whole floor). Draft → Computed → Posted. "Compute from Scans" builds one line per operator; "Post" creates one journal entry (screens 77, 78, 79). |
| `garment.wage.sheet.line` | Per operator: scans, pieces, minutes, days, efficiency, piece earnings, minimum, top-up, OT hours/pay, incentive, deduction, net payable. |
| `garment.scan` (inherit) | `wage_line_id`: the wage line that paid this scan. |

## Rules
- Piece earnings = earned minutes (Σ scan `minutes_earned`) × rate card minute value.
- Days = distinct scan dates (UTC); efficiency = minutes ÷ (days × hours/day × 60) × 100.
- Top-up = max(0, days × statutory minimum − piece earnings).
- Overtime pay = OT hours × (minimum/day ÷ hours/day) × multiplier.
- Incentive = piece earnings × incentive % when efficiency is strictly above the threshold.
- Net = earnings + top-up + overtime + incentive − deduction.
- A scan is claimed by one wage line only (`wage_line_id`); compute only picks unclaimed scans, so two sheets never
  count a scan twice. Reset/delete releases the scans; a posted sheet can't be reset or deleted.
- Post: one `entry` move on the sheet journal; per operator a debit on the wages expense account and a credit on
  the wages payable account (partner = employee work contact). Balanced by construction.

## API
`env["garment.wage.sheet.line"]._garment_wage_figures(card, minutes, days, overtime_hours=0, deduction=0)` → dict.

## Reports
Wage slip per operator (QWeb PDF `zyra_garment_wages.report_wage_slip`, screen 81), printed from the sheet.

## Security
Wages group and factory manager: full access. Scans are read/claimed with `sudo()`.

## Tests
Top-up, overtime, incentive threshold (at vs above), sheet from real scans, recompute stable, second sheet finds
no scans (no double count), empty sheet can't post, journal entry balanced and equal to net, posted sheet not deletable.

## Decisions
- Earnings use the rate card minute value, not the scan's own minute rate, so one card prices the whole sheet.
- Overtime hours are entered on the sheet line (no attendance link yet); kept across recomputes.
- Incentive threshold is strict (> threshold).

## Not done yet
- Screens 77–81 were not compared image by image (short time segment); views are plain list/form, no KPI tiles.
- No demo data. No attendance/hr leave link for days worked. No payment registration from the sheet.
