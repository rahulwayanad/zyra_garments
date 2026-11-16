# Architecture — 15 modules on Odoo 18 CE

Status: **proposed names** where the plan did not name a module (marked *). Confirm with Rahul before Day 1
creates them; renaming a module after install is painful.

## Layers

```
 Cockpits (zyra_garment_cockpit) · Portals (zyra_garment_portal) · API/webhooks/imports (zyra_garment_connect)
                         ── read every area below ──
 Tech pack + costing ─▶ Merchandising ─▶ Materials
        │
        ▼
 Cutting ─▶ Sewing floor ─▶ Quality ─▶ Packing & shipping
    │            │                          │
    ▼            ▼                          ▼
 Job work      Wages                     Order P&L
 ───────────────────────────────────────────────────────────
 zyra_garment_base — setup wizard, 11 roles, sizes, colourways, POM and defect libraries
 ───────────────────────────────────────────────────────────
 Odoo 18 CE — Sales, Purchase, Inventory (rolls as lots), Manufacturing, Invoicing, Employees, Portal, Discuss
```

## Module list (build order)

| # | Technical name | Day | Area | Depends on (ours) | Key Odoo touch-points |
|---|---|---|---|---|---|
| 1 | `zyra_garment_base` | 1 | Setup wizard, roles, settings, shared libraries (sizes & size ranges, colourways, points of measure, defect library, sewing lines, operators/badges), floor-screen theme assets | — | `res.config.settings`, `res.groups`, `hr.employee`, `product` |
| 2 | `zyra_techpack` (existing — refactor) | 1 | Style, versioned tech pack, measurement spec + grading, construction, BOM per colourway/size | base | `product.template` variants, `mrp.bom` |
| 3 | `zyra_garment_costing`* | 1 | Versioned cost sheet, margin floor, approval | techpack | `product.pricelist`, `sale.order` price |
| 4 | `zyra_garment_merch`* | 1 | Samples (rounds, fit measurements), approval cards (lab dip, strike-off, trim, wash), production order + size/colour grid, time & action | costing | `sale.order` (product matrix), `mail.activity` |
| 5 | `zyra_garment_materials`* | 2 | Fabric & trims bookings, rolls as lots (shade, shrinkage, width, GSM), 4-point inspection (tablet), roll issue, CMT buyer-owned fabric | merch | `stock.lot`, `stock.picking`, `purchase.order` |
| 6 | `zyra_garment_cutting`* | 2 | Markers (entered/imported), cut plan builder, lays, end loss, bundles, bundle ticket with QR coupon per operation, fabric reconciliation | materials | `stock.move` (fabric consumption) |
| 7 | `zyra_garment_jobwork`* | 2 | Job work orders (print, embroidery, wash, outsourced sewing), challan, receive-back, process loss, billing | cutting | `purchase.order`, `stock.picking` |
| 8 | `zyra_garment_quality`* | 2 | Inline/end-line checks (tablet), AQL plans & final inspection (blocks shipment), DHU, CAPA | cutting | `stock.picking` block |
| 9 | `zyra_garment_sewing`* | 3 | Operation library & bulletin (SAM, piece rate), line balancing, planning board, scan station (offline queue), TV line board, hourly output | cutting | `mrp.workcenter` (lines), OWL client actions |
| 10 | `zyra_garment_wages`* | 3 | Rate card, weekly wage sheets from scans, guaranteed-minimum top-up, overtime, incentive, wage slips, journal entry | sewing | `account.move` |
| 11 | `zyra_garment_shipping`* | 4 | Pack plans, cartons with SSCC, packing list, shipments, letters of credit, export documents | quality | `stock.picking`, `mrp.production` (finished goods posting) |
| 12 | `zyra_garment_pnl`* | 4 | Order P&L: planned vs actual material, making, other cost; margin | shipping, wages, jobwork | `account.move.line`, analytic |
| 13 | `zyra_garment_cockpit` | 4 | One cockpit per department (OWL dashboards) | all areas | OWL, `ir.actions.client` |
| 14 | `zyra_garment_portal` | 4 | Buyer portal (orders, progress by colour/size, T&A), job-work vendor portal | merch, jobwork | `portal` |
| 15 | `zyra_garment_connect` | 4 | REST API with keys & scopes, signed webhooks, CSV imports with dry run, First Steps checklist | all areas | `ir.http` controllers, `queue`-less cron retries |

## Cross-cutting rules

- **One production order per style** holds the whole size × colour grid; booking, cutting, sewing and packing all
  read that grid — entered once.
- **Garments are product variants; fabric rolls are `stock.lot`.** Stock value and COGS come from Odoo's own postings.
- **Finished goods:** when packed garments post to stock, create one `mrp.production` per variant for exactly that
  quantity, consuming the fabric issued.
- **Wages:** not a payroll. Piece-rate sheets → one `account.move`. No statutory deductions.
- **Scanning:** QR / barcode only (handheld wedge scanner, camera, or typed). No RFID, no machine connection.
- **Markers:** entered or imported (size ratio, length). We never draw or nest markers.
- **Standard minutes:** our own operation library and time study. No licensed time system (GSD etc.).
- **External services:** customs, banks, certifiers — registers and printed documents only, no live connection.
- **Every chart in a cockpit also reads as a table and exports.**

## Roles (11) — proposal

Reference app has 11 roles including two decoration roles we do not build. Proposed set:

1. Viewer (read only, cockpits)
2. Merchandiser — styles, samples, costing, orders, T&A
3. Fabric & Trims Store — receive, inspect, issue rolls and trims
4. Cutting Room — cut plans, lays, bundles, reconciliation
5. Line Supervisor / IE — bulletins, line plans, hourly output
6. Scan Operator — scan station only (badge login)
7. Quality Controller — inline, end-line, final inspections, CAPA
8. Job Work Coordinator — challans, receive-back, vendor billing
9. Packing & Shipping — cartons, packing lists, shipments, LCs
10. Wages & Finance — wage sheets, journal, order P&L
11. Factory Manager — everything, plus approvals, overrides, configuration

## Backlog (not before go-live, 11 Jan 2027)

Decoration & personalisation (team wear, rosters, print queue), compliance (audits, certificates, traceability),
made-to-measure / uniform contracts, AI document reading, Arabic/RTL.

## Open questions

- Where is the existing `zyra_techpack` repo? It is not in this workspace yet.
- Odoo 18 CE checkout / docker setup and PostgreSQL version for the Prove step.
- Confirm module names marked * and the 11 roles above.
- Currency and locale for the pilot factory (₹ / INR assumed in mockups).
