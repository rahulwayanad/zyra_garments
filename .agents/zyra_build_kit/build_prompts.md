# Zyra Garment ERP: Claude Code prompts, terminal by terminal

<?claude block asof?> · <?claude block me?>

## How to run it

The build runs in **five waves**. Terminals in the same wave work at the same time, because they touch different modules. Each wave waits for the one before it to be merged. Every terminal works in its own git worktree and branch, so they never edit the same files.

| Wave | Terminals running together | Modules | Waits for |
|---|---|---|---|
| 1 | T1 | zyra_garment_base | – |
| 2 | T2, T3, T4 | zyra_techpack (refactor), zyra_garment_costing, zyra_garment_merch | Wave 1 merged |
| 3 | T5, T6, T7, T8 | zyra_garment_materials, zyra_garment_cutting, zyra_garment_quality, zyra_garment_shipping | Wave 2 merged |
| 4 | T9, T10 | zyra_garment_sewing, zyra_garment_jobwork | Wave 3 merged |
| 5 | T11–T15 | zyra_garment_wages, zyra_garment_pnl, zyra_garment_cockpit, zyra_garment_portal, zyra_garment_connect | Wave 4 merged |

After every wave, run the **merge prompt** (M) in your main terminal, then start the next wave.

### One-time setup (main terminal)

```bash
mkdir zyra-garment && cd zyra-garment && git init
mkdir -p addons docs/screens docs/requests
# copy in: zyra_techpack/ and zyra_garment_theme/ -> addons/
# unzip zyra_screens_all.zip -> docs/screens/   (s001.jpg … s125.jpg + captions.json)
# save the CLAUDE.md below at the repo root
git add . && git commit -m "Start: techpack, theme, screens, CLAUDE.md"
```

Start each terminal of a wave like this (example for T4):

```bash
git worktree add ../wt-merch -b feat/merch
cd ../wt-merch && claude
```

Then paste that terminal's prompt. Use one database per terminal (`zyra_merch`, `zyra_cutting` …) so parallel test runs don't collide.

### CLAUDE.md (save at the repo root)

```markdown
# Zyra Garment ERP — rules for every session

Stack: Odoo 18 Community, Python 3.11+, PostgreSQL. Clean-room build: mn_garment (Odoo 19, OPL-1) is a
functional reference only. Never copy its code, names of its files, or its text.

## Layout
- addons/<module>/ — one module per department. Prefix: zyra_garment_ (zyra_techpack keeps its name).
- docs/screens/sNNN.jpg + captions.json — the target screens. Match their fields, states and KPIs.
- docs/requests/<module>.md — if you need a change in a module you don't own, write it here. Never edit it.

## Ownership
Only edit the module named in your prompt. Read any other module freely.

## Odoo 18 rules
- <list> not <tree>; invisible="…"/readonly="…" expressions, no attrs/states; <chatter/> in forms.
- Kanban: <t t-name="card"> with aside/main/footer.
- res.users.groups_id; product type: is_storable; Command API for x2many; copy_data returns a list.
- group_expand for kanban columns; _read_group for aggregates.
- Every model: _description, ir.model.access rows per role, record rules for multi-company.
- Translations: _() with self.env, never at module level.
- Money in company currency with currency_id; quantities with product UoM.

## Look
Depend on zyra_garment_theme. Use its classes: .o_zyra_kpis / .o_zyra_kpi (_good/_warn/_bad/_text)
for header KPI tiles, section headers, pill statusbar. Light theme only, no dark screens.

## Menus
Hang menus under the roots from zyra_garment_base (menu_garment_root and its section menus).

## Tests
Each module ships tests/ with TransactionCase tests for every state change and every computed figure.
Run: python odoo-bin -d zyra_<module> --addons-path=<odoo>/addons,addons \
     -i <module> --test-tags=/<module> --stop-after-init
A module is done only when it installs on an empty DB, all tests pass, and there are no warnings in the log.

## Done means
Installs clean · tests green · demo data shows every screen in your prompt · README.md in the module
with models, menus, and what other modules can rely on.
```

## Wave 1

### T1 — zyra_garment_base (run alone, everything depends on it)

```text
Read CLAUDE.md. Build addons/zyra_garment_base for Odoo 18 CE. It is the shared base every other
garment module depends on, so the names below are a contract: keep them exactly.

Depends: base, mail, product, stock, uom, hr, zyra_garment_theme.

Models (all with chatter where they are documents):
- res.partner: is_garment_buyer, is_jobwork_vendor, buyer_code.
- garment.season (name, code, year, active), garment.type (name, code, default SAM).
- garment.size.range (name, size_ids one2many ordered) + garment.size (name, sequence, range_id).
- garment.colour (name, code, pantone, hex).
- garment.pom (point of measure library: code, name, how to measure, default tolerance +/-).
- garment.defect (code, name, area, severity: minor/major/critical, department).
- garment.operation (code, name, machine_type_id, default SAM) + garment.machine.type.
- stock.lot extension for fabric rolls: is_fabric_roll, roll_status (received/approved/hold/rejected),
  dye_lot, shade_group, shrinkage_group, width_cm, gsm, points_per_100sqyd.
- res.company: minute_value, target_efficiency, working_minutes_per_day, margin_floor_pct.

Security: 11 groups under a "Garment" category: Merchandiser, Tech Pack Designer, Costing, Fabric Store,
Cutting, Line Supervisor, Quality, Packing & Shipping, Wages, Factory Manager (implies all the
others), Garment Admin. Access rows for every model.

Menus: menu_garment_root ("Garment") and section menus other modules hang under:
menu_garment_merch, menu_garment_materials, menu_garment_cutting, menu_garment_sewing,
menu_garment_quality, menu_garment_shipping, menu_garment_wages, menu_garment_reports,
menu_garment_config (holds every master above).

Setup wizard (garment.setup.wizard): company figures, size ranges from a preset (S-XL, XS-XXL, kids
2-14), load the POM and defect libraries from data files, assign users to roles. Screen 119 is the
target.

Data: POM library (~30 common points), defect library (~40, with severity), operation library for a
basic T-shirt and a 5-pocket jean, 3 size presets. Demo: 3 buyers, 2 seasons, 2 job-work vendors,
6 fabric rolls.

Tests: groups imply correctly, wizard creates size ranges and loads libraries once (idempotent),
roll status changes, company defaults.

When done: write the module README listing every model/field/xml id above, so wave 2 can build on it.
```

## Wave 2

### T2 — zyra_techpack refactor

```text
Read CLAUDE.md and addons/zyra_garment_base/README.md. You own addons/zyra_techpack only.

Refactor the existing zyra_techpack onto zyra_garment_base without losing behaviour:
- Add depends on zyra_garment_base. Replace techpack-local size, colour, POM and buyer fields with
  garment.size.range / garment.size, garment.colour (colourways), garment.pom, res.partner buyers,
  garment.season, garment.type. Write a migration (migrations/18.0.2.0.0) that maps old values.
- Keep: revisions (old version stays approved until the new one is approved, one open revision),
  links to product.template / mrp.bom / sale.order / mrp.production, the MO and SO gates,
  stock.rule passthrough, the printed tech pack.
- Add the measurement spec with grade rules and the graded chart with base size marked (screen 24),
  construction details per area: stitch class, SPI, seam type, allowance (screen 25).
- Move menus under menu_garment_merch; map existing roles to the base groups.
- Match screens 22–25 and 37.
All 12 existing tests must still pass; add tests for grading and the migration.
```

### T3 — zyra_garment_costing

```text
Read CLAUDE.md and the READMEs of zyra_garment_base and zyra_techpack. Build addons/zyra_garment_costing.
Depends: zyra_techpack, purchase.

- garment.cost.sheet linked to a techpack revision and buyer: material lines per colourway (from the
  techpack BoM: consumption, wastage %, price, share of order), trims, processes (wash, print,
  embroidery, job work) per piece or per order, making cost = SAM × company minute_value ÷ efficiency,
  overheads %, commission %, target price, FOB price, margin and margin %.
- States: draft → submitted → approved → superseded. Approval under company margin_floor_pct needs
  Factory Manager and a reason kept in chatter (screen 32).
- Approved sheet writes the planned cost onto the techpack and is what zyra_garment_merch prices from.
- List with sheets under the floor in red, KPI header (screen 31), printed internal cost sheet (38).
Tests: every formula with known numbers, floor rule, revision supersedes old sheet.
```

### T4 — zyra_garment_merch

```text
Read CLAUDE.md and the READMEs of zyra_garment_base and zyra_techpack. Build addons/zyra_garment_merch.
Depends: zyra_techpack, sale_management, sale_mrp.

- garment.style cards (screen 22) and style form with open orders, pieces, SAM, material cost and
  price left after material (screen 23). Style = techpack + its approved cost sheet if present
  (soft link: do not depend on costing; read it if installed).
- garment.order (production order) from a confirmed sale order: buyer, style, techpack revision,
  ex-factory date, line, state (draft/confirmed/in_production/packed/shipped/closed).
  garment.order.line = one row per colourway × size with qty_ordered and computed qty_cut, qty_sewn,
  qty_packed, qty_shipped (other modules will write these through a small API you define:
  _garment_add_progress(stage, colour_id, size_id, qty)). Grid entry widget (screen 34),
  breakdown report (35), open orders list with late in red (33).
- Samples: garment.sample (type: proto/fit/size-set/PP/TOP, round, dates, courier, cost, measurements
  against spec with verdict per point) — screens 26–28.
- Approvals: garment.approval (lab dip, strike-off, trim card, wash standard; options, buyer choice,
  comment) — screens 29–30.
- Time and action: garment.tna.template + per-order milestones with planned/actual dates, owner,
  on-time status (screen 36).
Document the progress API in the README; waves 3–4 depend on it.
Tests: grid totals, progress API, late flags, sample verdicts, T&A dates from template.
```

## Wave 3

### T5 — zyra_garment_materials

```text
Read CLAUDE.md and READMEs of base, techpack, merch. Build addons/zyra_garment_materials.
Depends: zyra_garment_merch, purchase_stock.

- garment.fabric.booking, one per garment.order: required qty per material per colourway from the
  techpack BoM × ordered qty × (1 + wastage), stock, open POs, rolls received, value still to order,
  short flag; button to raise POs (screens 39–40).
- Rolls are stock.lot with the base roll fields. Roll board kanban by roll_status (41), roll form (42).
- garment.fabric.inspection, 4-point system: defects with length band (≤3", 3–6", 6–9", >9" = 1–4 pts),
  points per 100 sq yd = points × 3600 ÷ (inspected yards × width inches), accept limit from company
  setting; fail puts the roll on hold with the reason (43–44). Tablet inspection screen as a client
  action, big tap targets, live points and verdict (45).
Tests: 4-point formula with known numbers, hold on fail, booking shortfall maths.
```

### T6 — zyra_garment_cutting

```text
Read CLAUDE.md and READMEs of base, techpack, merch. Build addons/zyra_garment_cutting.
Depends: zyra_garment_merch, stock.

- garment.cut.plan per order and colourway: pieces to cut vs planned per size, planned %, fabric to lay
  (screens 46–47). Plan builder wizard: from markers (garment.marker: size ratio, length, efficiency)
  propose lays that cover what's left per size; plies editable before approval (48).
- garment.lay: plies planned and spread, lay length, fabric laid, end loss, rolls/shades used
  (stock.lot), table, spreader, cutter (49). Confirming a lay consumes fabric and calls
  garment.order _garment_add_progress('cut', …).
- garment.bundle: order, colourway, size, lay, plies, roll, shade, pieces, line, stage
  (cut/issued/in_sewing/sewn/finished); kanban by stage (50–52).
- Printed bundle ticket: header + one tear-off QR coupon per operation from the techpack's operation
  list (53). The coupon payload format goes in the README; T9 scans it.
Tests: lay proposal covers sizes exactly, cut progress, bundle split by plies, coupon payload.
```

### T7 — zyra_garment_quality

```text
Read CLAUDE.md and READMEs of base, merch. Build addons/zyra_garment_quality.
Depends: zyra_garment_merch.

- garment.inspection: kind inline/end-line/final, order, line, pieces checked, defect lines
  (garment.defect, qty, position), DHU = defects × 100 ÷ pieces checked, result (61).
- Final inspection with AQL: lot size → sample size and accept/reject numbers from an AQL table
  (ISO 2859-1 general level II, AQL 2.5 major / 4.0 minor, as data), pass/fail with reason (62–63).
  A failed final blocks shipment: expose garment.order.final_passed for zyra_garment_shipping.
- Tablet end-line check: tap defect area and type; hourly and daily DHU update live (64).
- garment.capa raised from a repeated defect: occurrences, root cause, action, owner, due (65).
- Printed final inspection report (66).
Tests: AQL lookups at boundaries, DHU, final blocks shipment flag, CAPA trigger threshold.
```

### T8 — zyra_garment_shipping

```text
Read CLAUDE.md and READMEs of base, merch. Build addons/zyra_garment_shipping.
Depends: zyra_garment_merch, stock, account.

- garment.pack.plan per order: pack kind (solid/ratio/assorted), pieces per carton, cartons planned and
  packed, gross weight, CBM (67–68). garment.carton: content by colour × size, pieces, net/gross
  weight, CBM, SSCC-18 with check digit, shipment (69). Packing calls _garment_add_progress('packed').
- garment.shipment: buyer, orders, mode, port, planned/actual ex-factory, days late, cartons, value,
  LC, stage; ships through stock.picking; warns if final inspection not passed (read
  final_passed if zyra_garment_quality is installed, soft dependency) or LC expired; overrides need
  Factory Manager with reason (70–71).
- garment.lc: amount, drawn, balance, latest shipment date, expiry, days left, tolerance (72–73).
- Printed packing list (76).
Tests: SSCC check digit, carton maths, late days, LC balance, override rule.
```

## Wave 4

### T9 — zyra_garment_sewing

```text
Read CLAUDE.md and READMEs of base, merch, cutting. Build addons/zyra_garment_sewing.
Depends: zyra_garment_cutting, hr.

- garment.line (sewing line: operators, machines, capacity minutes). garment.bulletin per style:
  operations with section, machine, SAM, target/hour, piece rate (54).
- Line balancing wizard: pitch time, target and balanced output, balance loss %, bottleneck, operators
  per station (55).
- garment.scan: coupon, operator (hr.employee), line, order, bundle, operation, pieces, minutes earned
  = pieces × SAM, earnings = minutes × rate. Duplicate coupon refused. Last operation of a bundle
  moves it to sewn and calls _garment_add_progress('sewn') (57).
- Scan station client action: badge + coupon scan, works offline (IndexedDB queue, syncs on
  reconnect, duplicate-safe) — screen 4.
- Line TV board (hour by hour output vs target, efficiency, top operator) as a full-screen client
  action (56). Daily line summary: pieces, efficiency, lost minutes, WIP days, DHU if quality
  installed (58). Planning board: orders as bars on lines, load vs capacity (3).
Tests: efficiency maths, duplicate coupon, offline batch replay idempotent, bundle completes.
```

### T10 — zyra_garment_jobwork

```text
Read CLAUDE.md and READMEs of base, merch, cutting. Build addons/zyra_garment_jobwork.
Depends: zyra_garment_cutting, purchase, stock.

- garment.jobwork.order: vendor (is_jobwork_vendor), process (sewing/wash/print/embroidery), bundles or
  pieces sent, delivery challan out, returns (good/reject), process loss vs allowance %, rate,
  state sent/partly received/received/billed, overdue flag (59–60).
- Sending and receiving move stock to/from a vendor location; on receipt raise the PO/vendor bill at
  the agreed rate for accepted pieces only.
- Printed delivery challan.
Tests: loss vs allowance, partial receipts, billing quantity, overdue.
```

## Wave 5

### T11 — zyra_garment_wages

```text
Read CLAUDE.md and READMEs of base and sewing. Build addons/zyra_garment_wages.
Depends: zyra_garment_sewing, hr, account.

- garment.rate.card: minute value, hourly earnings at full efficiency, bulletins it prices (80).
- garment.wage.sheet weekly per line or floor: lines per operator from scans (pieces, minutes, days,
  efficiency, earnings), top-up to the statutory minimum, overtime, incentive over a target
  efficiency, net payable (77, 79). Post creates one journal entry (78).
- Printed wage slip per operator (81).
Tests: top-up, overtime, incentive thresholds, journal balances, sheet can't double-count scans.
```

### T12 — zyra_garment_pnl

```text
Read CLAUDE.md and READMEs of base, merch, costing, shipping, jobwork, wages. Build
addons/zyra_garment_pnl. Depends: zyra_garment_costing, zyra_garment_shipping, zyra_garment_jobwork,
zyra_garment_wages.

- garment.order.pnl (SQL view or computed report) per order: invoiced revenue, planned cost from the
  approved cost sheet, actual material (stock valuation of consumed moves), making (wage lines),
  job work (vendor bills), other cost, variance, margin, cost per piece (74–75).
- Pivot and graph views by buyer, style, month.
Tests: one order end to end with known numbers gives the expected margin and variance.
```

### T13 — zyra_garment_cockpit

```text
Read CLAUDE.md and every module README. Build addons/zyra_garment_cockpit. Depends on all
department modules.

- One OWL client action per cockpit, KPI tiles with the theme classes and charts (Chart.js already
  bundled in Odoo): Factory Pulse, Order Book, Costing and Margin, Samples and Approvals, Time and
  Action, Fabric Store, Cutting Room, Capacity and Plan, Job Work, Quality, Packing and Shipments,
  Wages and Productivity, Order Profitability (screens 1, 5–17). Every tile clicks through to the
  filtered list.
- Present mode: full screen for a floor TV, auto-refresh every 60 s (21).
- Data from one Python method per cockpit using _read_group; no N+1.
Tests: each cockpit's data method returns the right figures on demo data.
```

### T14 — zyra_garment_portal

```text
Read CLAUDE.md and READMEs of merch, shipping, jobwork. Build addons/zyra_garment_portal.
Depends: portal, zyra_garment_merch, zyra_garment_shipping, zyra_garment_jobwork.

- Buyer portal: home with their orders, late orders, styles (122); orders list with pieces
  ordered/packed/shipped, ex-factory, status (123); one order with progress by colourway per stage
  and their T&A milestones (124). Buyers approve samples and lab dips from the portal.
- Job-work vendor portal: jobs held, sent, expected back, pieces pending (125).
- Record rules so a portal user only sees their own partner's records. Light theme.
Tests: HttpCase portal pages render; a buyer cannot read another buyer's order.
```

### T15 — zyra_garment_connect

```text
Read CLAUDE.md and every module README. Build addons/zyra_garment_connect.
Depends: zyra_garment_base, zyra_garment_merch (soft-read others).

- garment.api.key: scopes (read/post per model), rate limit, expiry, call log (114). JSON REST
  controllers under /api/garment/v1 for orders, bundles, scans, rolls, cartons; Bearer auth;
  proper status codes; in-app API reference page (120).
- garment.webhook: endpoint, events (order confirmed, bundle cut, final failed, shipment left),
  HMAC-SHA256 signing, delivery log with retries via ir.cron (115).
- CSV import with dry run, row-by-row result before writing (118) for rolls, rosters, orders.
- First Steps checklist from empty DB to first scanned bundle (121). Connect cockpit (20).
- Optional document reading (116–117): only if the company sets its own AI API key; reads a buyer
  tech pack or PO into fields with confidence, user accepts or rejects each field.
Tests: scopes enforced, rate limit, webhook signature, dry run writes nothing.
```

## Merge prompt (M) — main terminal, after every wave

```text
Read CLAUDE.md. Merge the branches of the wave that just finished into main, one at a time:
<list the branches, e.g. feat/techpack feat/costing feat/merch>.
For each: git merge, resolve conflicts (keep both sides' intent; module code belongs to its owner),
then create a fresh DB and install every module on main together. Run all garment tests:
--test-tags=/zyra_garment_base,/zyra_techpack,… (every module present). Fix only integration issues
(manifest depends, xml ids, menu parents, access rows). Read docs/requests/*.md and list which
requests need the owning module's next session. Commit, remove the merged worktrees
(git worktree remove ../wt-<name>), and print a short report: modules installed, tests passed/failed,
open requests.
```

## When a terminal stops halfway

```text
Read CLAUDE.md and git log on this branch. Carry on with the module from where it stopped: run its
tests first, list what's failing or missing against the prompt below, then finish it.
<paste the terminal's original prompt>
```
