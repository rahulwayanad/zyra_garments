---
name: garment-domain
description: Garment cut-and-sew factory domain knowledge for the Zyra ERP — glossary (tech pack, POM, SAM, SMV, DHU, AQL, 4-point, lay, ply, bundle, coupon, T&A, ex-factory, FOB, CMT, SSCC, LC) and the business formulas and rules each module must enforce. Use when modelling, naming fields, writing business rules or tests for any garment module.
---

# Garment factory domain

Detailed per-area features: `.agents/docs/reference/feature-reference.md`. Rules below are defaults — confirm
factory-specific numbers with Rahul / the functional consultant, and make them **settings, not constants**.

## Glossary

| Term | Meaning |
|---|---|
| Style | A garment design (e.g. ST-0142 Five-pocket Chino). Has colourways and a size range. Product template. |
| Colourway | A colour version of a style. Variant attribute. |
| Size range / size set | Ordered sizes of a style (S–XXL, 28–36). Variant attribute. |
| Tech pack | Versioned spec of a style: sketch, BOM, measurement spec, construction, artwork, labels, packing. |
| POM | Point of measure (chest ½, body length…). Base-size value + tolerance ± + grade rule per size step. |
| Grade rule | Increment per size step from the base size → graded measurement chart. |
| Construction | Per garment area: stitch class (301, 401, 504…), SPI (stitches per inch), seam type, seam allowance. |
| Sample | Proto, fit, size-set, PP (pre-production), shipment sample. Rounds until approved. |
| Lab dip / strike-off / trim card / wash standard | Approval cards for colour, print, trims, wash. Buyer picks an option or asks to resubmit. |
| Cost sheet | Price build-up: fabric + trims + making + overheads + margin → FOB. Versioned. |
| FOB | Free on board — price includes everything to the port. Full-package model. |
| CMT | Cut-make-trim — buyer supplies fabric; factory invoices making charge; fabric reconciled back. |
| Production order (GO) | One per style; holds the full size × colour quantity grid. |
| T&A | Time & action calendar: milestones laid back from ex-factory date, each with owner, planned & actual date. |
| Ex-factory date | Date goods must leave the factory. Lateness is measured against it. |
| Fabric booking | Fabric requirement for an order: consumption × qty × (1 + wastage), per colourway. |
| Roll | One fabric roll = one `stock.lot`. Has length/weight, width, GSM, shade, shrinkage, dye lot. |
| 4-point system | Fabric inspection: defect length ≤3" = 1, >3–6" = 2, >6–9" = 3, >9" = 4 points (max 4 per linear yard). |
| Shade / shrinkage group | Rolls grouped so one lay / one garment never mixes shades. |
| Marker | Pattern layout for a size ratio on a given width; has length and efficiency %. Entered, never drawn. |
| Lay / spread | Plies of fabric laid on the cutting table under one marker. |
| Ply | One layer in a lay. Pieces cut = plies × marker ratio. |
| End loss | Fabric wasted at lay ends per ply. |
| Bundle | Group of cut pieces (one size, one shade, one colour) moved together, e.g. 20–30 pcs. |
| Bundle ticket / coupon | Ticket per bundle with one tear-off coupon (QR) per sewing operation. |
| Operation bulletin | List of sewing operations of a style: section, machine, SAM, target/hr, piece rate. |
| SAM / SMV | Standard allowed minute / standard minute value — time a trained operator needs per operation. |
| Line balancing | Assigning operations to operators/stations so the line flows; pitch time, bottleneck, balance loss. |
| Efficiency | (pieces × SAM) ÷ (operators × minutes worked) × 100. |
| DHU | Defects per hundred units = defects found ÷ pieces checked × 100. |
| AQL | Acceptable quality limit — sampling plan (ISO 2859-1 / ANSI Z1.4) giving sample size and accept/reject numbers. |
| Inline / end-line / final | Quality checks during sewing / at line end / on the finished lot before shipment. |
| CAPA | Corrective and preventive action raised from repeated defects. |
| Job work | Pieces sent to a vendor for print, embroidery, wash or sewing, and counted back. Challan = delivery note. |
| Pack plan | How an order is packed: solid (one size/colour per carton) or ratio (assortment). |
| SSCC | Serial Shipping Container Code — 18-digit GS1 code per carton (with mod-10 check digit). |
| LC | Letter of credit — bank payment instrument with amount, tolerance, latest shipment date, expiry. |
| Piece rate | Pay per piece per operation, normally SAM × value of a standard minute. |
| Guaranteed minimum | Statutory/agreed minimum wage; if piece earnings fall short, the difference is the top-up. |

## Formulas (make each a tested method)

- **Graded measurement** = base value + (size steps from base × grade rule).
- **Fit verdict** per POM = |measured − spec| ≤ tolerance → pass, else fail.
- **Fabric required** = Σ(order qty per cell × consumption per piece) × (1 + wastage %).
- **4-point score** = total points × 36 × 100 ÷ (inspected yards × fabric width in inches) → points per 100 sq yd.
  Typical accept limit 40 (setting). Above → hold/reject.
- **Pieces in a lay** = plies × Σ(marker size ratio).
- **Fabric laid** = plies × (marker length + end loss per ply).
- **Fabric utilisation** = marker area used ÷ fabric laid.
- **Making cost / pc** = SAM × cost per minute ÷ line efficiency.
- **FOB price** = (material + making + overhead) ÷ (1 − margin %). **Margin floor** below → manager approval.
- **Target / hour (line)** = operators × 60 × target efficiency ÷ style SAM.
- **Pitch time** = style SAM ÷ operators. Bottleneck = station with max (SAM ÷ operators at station).
- **Line efficiency** = Σ(pieces × op SAM) ÷ (operators × minutes worked).
- **Minutes earned (scan)** = pieces × operation SAM. **Earnings** = pieces × piece rate.
- **Top-up** = max(0, guaranteed minimum for days attended − piece earnings).
- **DHU** = defects ÷ pieces checked × 100.
- **Process loss (job work)** = (sent − good back) ÷ sent; compare to allowance.
- **Order P&L** margin = revenue − (material + making + job work + other); variance vs cost sheet.

## Hard rules

- The size × colour grid is entered **once** on the production order; every later step reads it.
- One lay never mixes shade groups; one bundle is one size + one shade + one colour.
- A coupon can be scanned **once**; a second scan is refused with who scanned it. Scans carry a client UUID so
  offline replays never double count.
- A failed final inspection **blocks** shipment of that lot until a re-inspection passes (manager override logged).
- A cost sheet under the margin floor cannot be approved except by Factory Manager, with a reason.
- Shipping after an LC's latest shipment date warns and needs an override.
- Wages: not a payroll — no statutory deductions; one journal entry per posted wage sheet.
- Every late flag is measured against the **ex-factory date**.
