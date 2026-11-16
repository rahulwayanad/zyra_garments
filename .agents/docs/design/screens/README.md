# Screen designs — the binding UI spec

Source: Claude Doc **"Zyra Garment ERP: Screen Designs"** — https://claude.ai/artifact/N9LcjqGyRDx62t6a4CnRYx
(125 screens planned, light theme, all names and data invented). **Every module's screens must follow these
designs strictly.** If a design and `../light-theme.md` disagree, the screen design wins — update light-theme.md.

Status (16 Nov 2026): all 125 images are here. Screens 1–100 were downloaded from the artifact's asset store in
upload order (`001-…jpg` to `100.jpg`); 1–70 carry slugs from the index below, 71–100 are unnamed until the doc
places them. Screens 101–125 are in this same folder as `s101.jpg` … `s125.jpg`.
Checked 16 Nov 2026: 125 files, numbers 1–125 with no gaps, no duplicate images, all readable.

## Build strictly as designed (Rahul, 16 Nov 2026)

Build each screen **exactly as it is in its image** — no reinterpretation, no "improvements":

- Same layout, sections, order of elements, and which elements exist (add nothing, drop nothing).
- Same field labels, column headers, column order, button names, tab names, menu names and menu order.
- Same states/badges and their colours, same KPI tiles, charts and their order.
- Same colours, spacing and type as seen; where a token in `../light-theme.md` or `tokens.scss` differs from
  the image, **the image wins** — fix the token.
- Demo data should reproduce what the image shows (invented names already).
- If Odoo 18 CE truly cannot render something as shown, stop and ask Rahul; do not substitute silently.
- Prove step: open the built screen next to its image and compare before merging.

## Where the files go

Save each image here as `NNN-<slug>.jpg` (`001-sewing-floor-cockpit.jpg`, …). The artifact's assets are stored
in screen order: the n-th uploaded image is screen n (verified by sha256 for screens 1–32).

## Index (screen → module)

| # | Screen | Module |
|---|---|---|
| 1 | Sewing floor cockpit | zyra_garment_cockpit |
| 2 | Production order running late | zyra_garment_merch |
| 3 | Line planning board | zyra_garment_sewing |
| 4 | Scan station | zyra_garment_sewing |
| 5–20 | Cockpits: Factory Pulse, Order Book, Costing & Margin, Samples & Approvals, Time & Action, Fabric Store, Cutting Room, Capacity & Plan, Job Work, Quality, Packing & Shipments, Wages & Productivity, Order Profitability, Compliance*, Made to Measure*, Connect | zyra_garment_cockpit |
| 21 | Present mode (cockpit full screen for a floor TV) | zyra_garment_cockpit |
| 22–25 | Style cards, style form, tech pack measurement spec, tech pack construction | zyra_techpack |
| 26–30 | Sample room board, size-set sample, fit measurements, approval cards, lab dip approval | zyra_garment_merch |
| 31–32 | Cost sheets, cost sheet approved under margin floor | zyra_garment_costing |
| 33–36 | Open production orders, size & colour grid, order breakdown, time & action plan | zyra_garment_merch |
| 37 | Printed tech pack | zyra_techpack |
| 38 | Printed internal cost sheet | zyra_garment_costing |
| 39–45 | Fabric bookings, booking, rolls board, roll (lot), inspections, 4-point inspection on hold, tablet inspection | zyra_garment_materials |
| 46–53 | Cut plans, cut plan, cut plan builder, lay, bundles, bundles by stage, bundle, printed bundle ticket | zyra_garment_cutting |
| 54–58 | Operation bulletin, balanced line, line TV board, scans, daily line summary | zyra_garment_sewing |
| 59–60 | Job work orders, outsourced sewing job | zyra_garment_jobwork |
| 61–66 | Inspections, final inspections, failed final with AQL plan, tablet end-line check, CAPA, printed final inspection report | zyra_garment_quality |
| 67–70 | Pack plans, pack plan in progress, cartons, shipments | zyra_garment_shipping |
| 71–125 | Not yet in the doc: rest of packing & shipment (LCs, order P&L), wages, compliance*, made to measure*, decoration*, connect & portals | — |

\* backlog after go-live (see `../../architecture.md`), designed now, built later.

Update this index when the doc is complete.
