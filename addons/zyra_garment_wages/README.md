# zyra_garment_wages

Operator wages for the Zyra garment ERP (Odoo 18 CE): piece-rate wage sheets built from sewing coupon scans,
top-up to the statutory minimum, overtime, an efficiency incentive, one journal entry per sheet, and a printed
wage slip per operator.
Depends: `zyra_garment_base`, `zyra_garment_theme`, `zyra_garment_sewing`, `hr`, `account`.

## Models
| Model | Purpose |
|---|---|
| `garment.rate.card` (RC/YYYY/nnnn) | Draft → Active. Basis (standard minute value), value of a standard minute, earnings per hour at 100 % (= value × 60), guaranteed daily minimum, top-up period (daily / weekly), overtime rate (× hourly minimum), valid from, hours per day, incentive threshold and %, priced bulletins. "Apply to Bulletins" sets each bulletin operation's piece rate = SAM × minute value (hand-typed rates are kept) and stamps the bulletin's rate card and date. |
| `garment.wage.sheet` (WS/YYYY/nnnn) | Weekly sheet for one sewing line or the whole floor (line empty). Draft → Computed → Approved → Posted (+ Cancelled). Period label "Week NN · Line 2 / whole floor". KPIs: operators, piece earnings, minimum top-up, below minimum (operators topped up), overtime, incentive, net payable. |
| `garment.wage.sheet.line` | One operator: badge, line (where most of the scans are), paid by (piece / time rate), scans, pieces, minutes, days, efficiency, piece earnings, minimum, top-up, OT hours / pay, incentive, deduction, net pay. Frozen once the sheet is approved. |
| `garment.scan` (inherit) | `wage_line_id`: the wage line that pays this scan. |
| `hr.employee` (inherit) | `garment_paid_by`: piece rate (default) or time rate. |
| `garment.bulletin` (inherit) | `garment_rate_per_minute` = labour per piece ÷ total SAM (shown on the rate card). |

## Rules (`garment.wage.sheet.line._garment_wage_figures(card, day_minutes, overtime_hours, deduction, paid_by)`)
- Piece earnings = earned minutes (Σ scan `minutes_earned` = pieces × SAM) × the card's value of a standard minute.
- Days = distinct scan dates (UTC); efficiency = minutes ÷ (days × hours per day × 60) × 100.
- Top-up, weekly: max(0, days × daily minimum − earnings). Daily: Σ over days max(0, daily minimum − that day's
  earnings), so a strong day doesn't cover a weak one. A time-rate operator is always topped up weekly.
- Overtime = OT hours × (daily minimum ÷ hours per day) × overtime rate.
- Incentive = piece earnings × incentive % when efficiency is strictly above the threshold; piece rate only.
- Net = earnings + top-up + overtime + incentive − deduction.
- "Compute from Scans" takes the period's scans that no wage line has claimed yet (and, if set, only of the
  sheet's line), groups them per operator and claims them. Recompute keeps typed OT hours and deductions. A scan
  is never paid twice; reset to draft releases them.
- Approve records who and when. Post creates one posted `entry` move on the sheet's journal: per operator a debit
  on wages expense and a credit on wages payable (partner = employee's work contact), dated the period end, and
  logs "Posted journal entry … The scans and attendance days paid by this sheet are now locked."
- Cancel Posted Sheet reverses the entry (cancel reversal), releases the scans for a corrected sheet and
  sets the sheet Cancelled (its lines then show zero; the chatter keeps both entry numbers).
- A posted sheet can't be deleted or reset.

## Screens → views
| Screen | View |
|---|---|
| 77 Wage sheets list | `view_garment_wage_sheet_list` (menu Garment › Wages › Wage Sheets): Sheet, Period and Scope, Operators, Pieces, Piece Earnings, Minimum Top-up, Overtime, Incentive, Net Payable, State badge. |
| 78 Posted wage sheet | `view_garment_wage_sheet_form`: Print Wage Slips / Cancel Posted Sheet, statusbar Draft·Computed·Approved·Posted, stat buttons Scans Paid and Journal Entry, six KPI tiles, name + period title, tabs Wage Lines / Approval & Posting / Notes, chatter. |
| 79 Wage sheet lines | `view_garment_wage_sheet_line_list` + search (menu Wages › Wage Sheet Lines; filter by sheet): Badge, Operator, Line, Paid By, Pieces, Minutes, Days, Efficiency, Piece Earnings, Top-up, Overtime, Net Pay. |
| 80 Rate card | `view_garment_rate_card_form` (menu Wages › Rate Cards): Apply to Bulletins, statusbar Draft·Active, KPI tiles, RC/ number + name, Rate and Rules groups, Priced Bulletins tab (Bulletin, Style, Operations, Total SAM, Rate / Std Minute, Piece Cost), chatter. |
| 81 Wage slip | QWeb PDF `zyra_garment_wages.report_wage_slip` on `garment.wage.sheet.line` (one page per operator; the sheet's "Print Wage Slips" prints all lines): title "Wage Slip · Week NN", badge · operator · line · department, period / paid by / days attended / efficiency box, Work done grouped by order and operation (pieces, SAM, minutes, earnings), Pay box. |

## API other modules can rely on
- `env["garment.wage.sheet.line"]._garment_wage_figures(card, day_minutes, overtime_hours=0, deduction=0, paid_by="piece")` → dict of the figures above.
- `garment.scan.wage_line_id` set = the scan is paid (P&L can read `wage_line_id.net_payable` for labour cost).
- `wage_line._garment_work_done()` → `[{order, operation, pieces, sam, minutes, earnings}]`.

## Security
Wages role and factory manager: full access to rate cards, sheets and lines, and read access to journals. The
wages role computes, approves, posts and prints without accounting or HR-officer rights: the journal entry is
written as superuser after the checks; badge and department are copied onto the wage line. The Journal Entry stat
button and field show only to users with accounting read access. Multi-company record rules on all three models.

## Demo
Four invented operators (OP1018 Meera Thomas, OP1019 Vineetha P, OP1030 Shaji T, OP1031 Anu Varghese, dept "Knit
Tops") plus the ten badge operators of the base demo. The demo scans the open coupons of the issued bundles over
three weeks; three fast operators work two long days and earn above the minimum, the rest are topped up; two are
paid by time rate. Result: two posted whole-floor sheets (weeks −2 and −1, with overtime) and a computed Line 2
sheet for this week where no one needs a top-up. Rate cards: "Piece rates · standard minute value" (active,
1.80 / minute, minimum 550 / day, incentive above 70 %, priced on every demo bulletin) and an archived 2025 card. Accounts WAGEXP / WAGPAY
are created for the demo.

## Tests (`tests/test_wages.py`, 11)
Weekly top-up, daily top-up per day, overtime, incentive threshold (at vs above), time rate (no incentive,
weekly top-up), rate card hourly + Apply to Bulletins (manual rates kept, draft card refused), sheet from real scans
→ approve → post (no double count, recompute keeps OT, frozen after approval, balanced entry = net, chatter line,
posted sheet not deletable), cancel posted (reversal, scans freed for a new sheet), period/line filtering, wage slip
work-done rows + QWeb render, wages clerk runs the week without accounting/HR rights.

## Decisions
- Earnings use the rate card's minute value, not each scan's stored minute rate, so one card prices the sheet.
- Screen 80 shows only Rate and Rules; hours per day and the incentive threshold / % (required by the kit) are
  added at the end of Rules.
- Statusbar adds Approved between Computed and Posted (screen 78); Cancelled is hidden from the bar.
- Overtime hours are typed on the wage line (no attendance link); a time-rate operator gets no incentive.
- Days are distinct scan dates. The money KPIs show full amounts, not lakh short forms ("₹4.71 L").
- A cancelled sheet keeps its lines but they show zero once their scans are released.
- The sheet's period, line and rate card are edited on the Approval & Posting tab (screen 78 has no header group).

## Not done yet
- No attendance / leave link for days worked; no payment registration from the sheet.
- Not opened in a browser (no browser tool in this run); views were checked by install and tests only.
