# Feature reference — what the reference app does, by area

Summarised **in our own words** from the app-store page of *Garment Factory ERP* (`mn_garment`, Odoo 19, OPL-1).
Use it to decide scope and rules. **Clean-room:** never copy its code, images, labels or text — see skill
`reference-app`. Screens: `screenshots-index.md`. Original page: `reference-app-store-page.pdf`.

Tags: **[MVP]** in our 4-day build · **[LATER]** backlog after go-live.

## Who it serves
Export (FOB / full-package) factories, CMT units (buyer-owned fabric, reconciled in a fabric statement while the
making charge is invoiced), own-brand / uniform makers, decorators [LATER], made-to-measure workshops [LATER].

## The flow in 8 steps
1. **Style & tech pack** — measurement spec graded over the size range, construction, artwork, labels, packing
   instructions; versioned; prints as one document. [MVP]
2. **Samples, approvals, price** — sample requests with fit measurements; lab dip / trim approval cards; cost sheet
   building price from fabric, trims, making cost, overheads. [MVP]
3. **Order & calendar** — one production order holds the size × colour matrix; time & action plan laid back from the
   ex-factory date, each milestone with an owner. [MVP]
4. **Fabric store** — bookings from the order, rolls received as lots, 4-point inspection, grouped by shade and
   shrinkage, issued roll by roll. [MVP]
5. **Cutting table** — cut plan from entered marker data, lays with plies and end loss, numbered bundles, ticket with a
   QR coupon per sewing operation. [MVP]
6. **Sewing line** — operation bulletin with standard minutes, balanced line, plan on the board, operators scanning
   coupons, output vs target hour by hour. [MVP]
7. **Quality & job work** — end-line checks on tablet, AQL final inspection, corrective actions; pieces out for print /
   embroidery / wash, counted back. [MVP]
8. **Packing, shipment, pay** — cartons vs pack plan, packing list, shipment and documents, weekly wage sheet from
   scans, order profit. [MVP]

## Area detail

### Merchandising [MVP]
- Style cards: sketch, buyer, garment type, colourways, SAM, approved-for-production flag.
- Style header strip: open orders, pieces on order, variants, SAM, material cost/pc, price left after material.
- Tech pack measurement spec: point of measure, base-size value, tolerance (+/−), grade rule → graded chart per size.
- Construction: per garment area — stitch class, SPI, seam type, seam allowance.
- Sample room board: requested → in making → with buyer → rejected / due again; required date; overdue flag.
- Sample record: round, required & decision dates, POM measured vs out of tolerance, courier, making cost.
- Fit measurements: each POM vs spec & tolerance → deviation and verdict per point.
- Approval cards: lab dip, strike-off, trim card, wash standard; options sent, option approved, resubmit, buyer comment.
- Cost sheet: material + making cost/pc; target vs FOB price; margin; **margin floor** (below = red, needs approval
  with reason); making cost = SAM × cost per minute ÷ line efficiency.
- Production orders list: ordered, cut, sewn, packed, shipped; packed %; line; ex-factory date; late in red.
- Size × colour grid (entered once) and breakdown per cell: ordered / cut / sewn / packed / shipped / balance.
- Time & action: milestone, planned vs actual date, owner, on-time / late.
- Prints: tech pack, cost sheet (internal), open costing (buyer), production order, order confirmation, order status, T&A chart.

### Materials [MVP]
- Fabric booking per order: date needed in house, % received, value to order, short bookings flagged.
- Booking lines per colourway: consumption, wastage, required qty, stock, open POs, rolls received.
- Roll = `stock.lot`: status (received / on hold / approved / rejected), qty, points per 100 sq yd, shade group,
  shrinkage group, supplier lot, measured width, GSM, dye lot.
- 4-point inspection: length inspected, defects with length band (≤3" = 1, 3–6" = 2, 6–9" = 3, >9" = 4 points),
  points/100 sq yd vs accept limit → pass / hold / reject, inspector's reason. Tablet screen: pick defect, tap band at position.
- CMT: buyer-owned rolls in stock, issued roll by roll, fabric statement.
- Prints: fabric booking, trims booking, roll label, fabric inspection report, CMT fabric statement.

### Cutting [MVP]
- Markers entered/imported (size ratio, length, width, efficiency). No marker drawing.
- Cut plan: pieces to cut vs planned per colourway; fabric to lay; number of lays; draft → approved → cutting.
- Builder: remaining qty per size, proposed lays from markers, editable plies before approval.
- Lay: plies planned vs spread, lay length, fabric laid, end loss, shades used, table, spreader, cutter, bundles made.
- Bundle: order, colourway, size, cut no., shade, roll, pieces good / rejected, line, stage (cut → issued → in sewing →
  sewn → finished → packed), operations scanned.
- Bundle ticket: header (order, colour, size, cut, plies, shade, roll) + one tear-off coupon per operation, each with QR.
- Prints: cut plan, lay slip, bundle tickets, cutting report, fabric reconciliation.

### Sewing floor [MVP]
- Operation bulletin: operation, section, machine, SAM, target/hour, piece rate; total sewing SAM.
- Line balancing: pitch time, target & balanced output/hour, balance loss, bottleneck, operators per station, capacity.
- Planning board: orders as bars per line; weekly load vs capacity (minutes); late vs ex-factory red; clashes flagged;
  drag to another day/line; live plan vs what-if copy; unplanned orders queue.
- Scan station: badge → coupon; shows pieces, minutes, earnings, % of day target; **offline queue, sends on reconnect**;
  duplicate-scan refusal.
- TV line board: output vs target so far, efficiency, target/hour, top operator, hour-by-hour bars.
- Scans log: operator, line, order, bundle, operation, pieces, minutes earned, amount.
- Daily line summary: pieces, efficiency, lost minutes, WIP days, DHU.
- Prints: operation bulletin, line layout, skill matrix, hourly production report.

### Job work [MVP]
- States: sent → partly received → received → billed; process (print / embroidery / wash / outsourced sewing), vendor,
  pieces good & pending; overdue flagged.
- Order: sent, good back, rejected, short; process loss vs allowance; rate/pc; PO for billable qty.
- Prints: job work challan, job work reconciliation.

### Quality [MVP]
- Inspections: inline / end-line / final; pieces checked; critical / major / minor; DHU; result.
- Final inspection per lot offered: AQL plan (lot size → sample size, accept/reject numbers for major & minor);
  **failed final blocks the shipment** until re-inspection passes. AQL tables ship as editable data.
- End-line tablet: tap defect location on garment, tap defect; hour & day DHU on screen.
- CAPA from repeated defect: source, count, root cause, action, owner.
- Red card for operators over the defect limit.
- Prints: inspection report, CAPA report, buyer claim, needle log sheet.

### Packing & shipment [MVP]
- Pack plan per order: pack kind (solid / ratio), pcs per carton, cartons planned vs packed, gross weight, volume.
- Carton: content by colour × size, pieces, net/gross weight, volume, **SSCC**, shipment.
- Shipment: buyer, orders, mode, port, planned vs actual ex-factory, days late, cartons, pieces, value, LC, stage;
  manager overrides logged.
- Letter of credit register: amount, drawn, balance, latest shipment date, expiry, days left, tolerance; warn when
  shipping after LC latest date.
- Prints: packing list, carton label, carton marks sheet, commercial invoice, CoO data sheet, inspection certificate,
  beneficiary certificate.

### Wages [MVP] — not a payroll
- Weekly wage sheet per line or floor: operators, pieces, minutes, days attended, efficiency, piece earnings,
  **top-up to guaranteed minimum**, overtime, incentive, net payable → journal entry.
- Rate card: value of a standard minute; hourly earning at 100% efficiency; prices the bulletins.
- Prints: wage slip (work by order & operation), wage sheet summary.

### Order P&L [MVP]
- Per order: revenue invoiced, planned vs actual material / making / other cost, cost variance, margin vs planned,
  cost per piece; loss-making orders flagged. Print: order P&L.

### Cockpits [MVP]
Pattern: **one sentence naming the worst thing → rail of KPI readings → charts.** Filters: period, buyer, line,
business model. Every chart readable as a table and exportable. Day/night theme per user.

| Cockpit | Question it answers |
|---|---|
| Factory Pulse | How many orders open, how far each stage, what is late today? |
| Order Book | Which orders are past/at risk vs ex-factory; pieces still to cut, sew, pack? |
| Costing & Margin | What is each price made of; which cost sheets are under the floor? |
| Samples & Approvals | What does the sample room owe; which approvals sit with the buyer? |
| Time & Action | Which milestones are overdue, on which orders, who owns them? |
| Fabric Store | What is on the racks, waiting inspection, bookings not covering orders? |
| Cutting Room | Cut vs plan, marker yield, end loss? |
| Sewing Floor | Is each line on target this hour; which is furthest behind? |
| Capacity & Plan | Standard minutes booked per line per week; clashes? |
| Job Work | Pieces out, with whom, how long, at what loss? |
| Quality | DHU, top defects, finals blocking shipment? |
| Packing & Shipments | Packed, on the way, late shipments, LCs expiring? |
| Wages & Productivity | Scan earnings, minimum top-up cost, labour cost per minute? |
| Order Profitability | Earned vs planned cost per order? |
| Connect | API, webhooks, portal, imports healthy? |

### Portal & Connect [MVP]
- Buyer portal: their orders, late ones, styles; per order progress by colour × size per stage, T&A milestones.
- Vendor portal: job work held, sent/expected dates, pieces pending.
- API keys: scopes (read/post), rate limit, expiry, calls & refusals. Endpoints: styles, orders, bundles, rolls, scans.
- Webhooks: endpoint, events, delivery log, signed requests (HMAC), retries.
- CSV import with row-by-row **dry run** before writing.
- Factory Setup: business models, menu areas shown, working minutes/day, target line efficiency, user roles.
- First Steps checklist: empty DB → first scanned bundle.

### [LATER] Compliance · Made to measure · Decoration · Document reading · Arabic RTL
See the PDF pages 52–76 if these come back into scope.

## Explicitly out of scope (also for the reference app)
Marker making / nesting / CAD; licensed time systems; RFID & machine connections; statutory payroll; live
customs/bank/certifier connections; printer/RIP control; colour management.
