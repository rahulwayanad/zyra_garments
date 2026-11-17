# One full sale, end to end: Coastline Outfitters · ST-0201 Organic Crew Tee

This is the demo story that `zyra_garment_suite` loads, starting from a buyer's enquiry and ending with the cash
in the bank. One order passes through all 14 modules. Every figure comes from a real document, created by the
modules' own buttons and APIs (`addons/zyra_garment_suite/models/suite_story_demo.py`); nothing is typed in by
hand. Use it to demo the system, train key users and review the screens with the functional consultant.

- **How to get it:** install `zyra_garment_suite` with demo data (`--without-demo=`). The story loads after
  every module's own demo. Tests: `addons/zyra_garment_suite/tests/test_full_sale_demo.py`.
- **Dates** are relative to the install day (called **D** below). The sale order is confirmed on D−80 and the
  money arrives on D. The calendar dates in brackets are from an install on 17 Nov 2026.
- **Document numbers** (PO/2026/0011, S00027 …) come from a fresh install of the suite with demo data. They
  shift if other records were created first. The demo's xml ids (`zyra_garment_suite.story_*`) do not shift.
- **Money** is in USD (the demo company currency). The rest of the demo uses a rupee-scale wage card; this
  story's sewing line has its own USD card at the costing minute value, so its P&L adds up.

## The order at a glance

| | |
|---|---|
| Buyer | **Coastline Outfitters**, Bristol (code CLO), new account |
| Style | **ST-0201 Organic Crew Tee**, SS27 · Organic Essentials, single jersey 180 gsm, SAM 6.95 |
| Grid | Sage 700 (S 100 · M 200 · L 250 · XL 150) + Optic White 400 (S 50 · M 100 · L 150 · XL 100) = **1,100 pcs** |
| Price | USD **4.95 FOB** Kochi (cost sheet v2, approved below the margin floor) → order value **USD 5,445.00** |
| Ex-factory | D−5 (12 Nov), shipped on time by sea to Felixstowe under LC **LCCLO71148** |
| Result | Cut 1,122 · sewn 1,116 · packed 1,100 · shipped 1,100 · invoiced and paid · **margin 19.0 %** against 7.5 % planned |

```
Enquiry ─► Tech pack ─► Fit sample ─► Cost sheet v1 ─► Quote ─✗─► Cost sheet v2 (below floor, FM) ─► Sale order
   ─► Production order + T&A ─► Lab dip · trim card · PP sample
   ─► Fabric & trims booking ─► POs ─► Rolls received ─► 4-point inspection
   ─► Markers ─► Cut plan ─► Lays ─► Bundles + QR coupons ─► Print job work (out and back)
   ─► Line 5: bulletin, rate card, coupon scans ─► Inline / end-line checks
   ─► Pack plan ─► 44 SSCC cartons ─► Final AQL inspection ─► Post to stock (MOs)
   ─► Letter of credit ─► Shipment ─► Ex-factory (delivery) ─► On board ─► Documents ─► Invoice ─► Paid
   ─► Wage sheet (journal entry) ─► Order P&L ─► Order completed
```

---

## 1. Enquiry, style and tech pack · D−96 to D−95

**Who:** merchandiser (Anjali Menon) and tech pack designer, then the Factory Manager approves.
**Where:** Garment Suite › Merchandising › Styles / Tech Packs. Screens 22–25, 37.

1. The buyer's brief CLO-T-2207 arrives: 1,100 organic crew tees, two colourways, target price USD 4.60 FOB.
2. The merchandiser creates the buyer (Merchandising › Buyers, `is_garment_buyer`, code CLO), the colour **Sage**
   (Pantone 16-0213 TCX, #9CAF88) and the style **ST-0201** (type T-shirt, knit, size range S–XL, colourways
   Sage + Optic White, sketch).
3. Tech pack **ST-0201 · v1** is filled in:
   - **Materials (BoM per colourway):** jersey 1.15 m/pc + 5 % wastage per colourway; neck rib, neck tape, thread,
     main label, GOTS care label, hangtag; polybag.
   - **Measurement spec:** 9 points of measure on base size M with tolerances and grade rules → graded chart
     S–XL (screen 24).
   - **Construction:** 6 seams (514 overlock, 406 twin-needle hems, screen 25).
   - **Operations:** the 12 T-shirt operations TEE-01…12 from the library. **SAM 6.95 min.**
   - Artwork, label and packing notes (25 pcs per carton, solid colour/solid size).
4. *Submit* (merchandiser) → *Approve* (Factory Manager only). On approval the style becomes **Approved for
   Production**, the system creates **8 product variants** (2 colours × 4 sizes) and generates the **Odoo BoM**.
   Material cost: USD 3.29 a piece (dearest colourway).

**Fit sample SMP/2026/0013** (Merchandising › Samples, screens 26–28): requested D−94, *Start*, *Load Spec* pulls the
graded size-M spec from the tech pack, 9 points measured (all inside tolerance, 0 out), sent D−90, approved D−87
("Fit approved. Go ahead with costing.").

> Rule shown: no sale or manufacturing order can be confirmed for a style without an approved tech pack.

## 2. Costing, quotation and the price negotiation · D−86 to D−82

**Who:** merchandiser / costing; the Factory Manager for the below-floor approval.
**Where:** Merchandising › Cost Sheets. Screens 31, 32, 38.

Cost sheet **CS/2026/0007 · ST-0201 · v1**, quantity basis 1,100, loaded from the tech pack BoM automatically:

| Per piece (USD) | v1 | v2 |
|---|---|---|
| Fabric (jersey, with wastage) | 2.90 | 2.90 |
| Trims and packing | 0.39 | 0.39 |
| Processes: chest print 0.18 (Sunrise Prints) + lab tests 150 ÷ 1,100 + packing 0.06 | 0.38 | 0.38 |
| Making: 6.95 SAM × 0.0573 ÷ 62 % efficiency | 0.64 | 0.64 |
| **Cost** | **4.30** | **4.30** |
| Commercial & finance 3 % of FOB | 0.16 | 0.15 |
| Margin (share of FOB) | 14 % = 0.73 | **10 % = 0.49** |
| **FOB** = cost ÷ (1 − 3 % − margin %) | **5.19** | **4.95** |
| CIF (+ freight 0.12) | 5.31 | 5.07 |

1. v1 is submitted and approved by Costing (14 % is above the 12 % floor).
2. *Create Quotation* → **S00026** for 1,100 pcs at 5.19 (USD 5,709), sent to the buyer.
3. The buyer counters at USD 4.90. The quotation is cancelled (chatter note) and the costing desk makes **v2**
   (*New Version*) at 10 % margin → FOB **4.95**.
4. 10 % is **under the 12 % margin floor**, so Costing cannot approve it. Only the Factory Manager can, and the
   approve wizard demands a reason: *"New buyer, first order: price agreed at the counter to open the account;
   repeat orders to be quoted at 14 %."* The reason is kept on the sheet and in the chatter. The FOB tile turns
   red. v1 becomes **superseded**.

## 3. Sale order → production order · D−84 to D−80

**Who:** merchandiser. **Where:** Sales › Orders, then Merchandising › Production Orders. Screens 2, 33–36.

1. Sale order **S00027**, customer ref (buyer PO) **CLO-PO-55120**, incoterm FOB, 8 lines (one per variant)
   at 4.95 → USD 5,445.00 untaxed. Sent, then **confirmed** on D−80.
2. Confirming the sale order opens **production order PO/2026/0011** automatically: buyer, style, tech pack v1,
   the 2 × 4 size/colour grid from the order lines, price 4.95, buyer PO, state **Confirmed**, and the bulk
   **T&A template** "Bulk order – 8 weeks" (11 milestones counted back from ex-factory D−5).
3. The order form shows the planned cost per piece from the approved cost sheet (material 3.29, making 0.64,
   other 0.65, margin 10 %) and the KPI strip: ex-factory, cut / sewn / packed / shipped, order value, PP sample,
   T&A, margin.

> From here on, no floor module writes quantities on the order. Cutting, sewing, packing and shipping each call
> the **progress API** (`_garment_add_progress`), and every number on the order traces back to a posting
> (Reports › Production Postings, 84 postings by the end).

## 4. Development: lab dip, trim card, PP sample, T&A · D−78 to D−48

**Where:** Merchandising › Approvals (screens 29–30), Samples, Time and Action.

- **Lab dip APR/2026/0009 (Sage, jersey):** options A/B/C sent D−78; buyer: "all three too yellow under D65", asks to
  resubmit; second submission D−72; **option B approved** D−69 (submission 2, 9 days to approval).
- **Trim card APR/2026/0010:** labels, hangtag and neck tape approved D−67.
- **PP sample SMP/2026/0014 (Sage, size M, bulk fabric and print):** requested D−60, measured against the graded spec,
  sent D−52, **approved D−48** ("Keep the neck rib at 2 cm"). The order's PP-sample tile turns green.
- **T&A:** milestones are marked done as the work happens. *Lab dips approved* finished **1 day late** and
  *PP sample approved* **2 days late**; the other 9 milestones were on time. The order ends with 11/11 done and
  none overdue.

## 5. Materials: booking, purchase, rolls, 4-point inspection · D−76 to D−49

**Who:** fabric store (Vivek Nair). **Where:** Materials › Fabric Bookings, Fabric Rolls (board), Fabric
Inspections, Inspection Tablet. Screens 39–45.

1. **Fabric booking FB/2026/0009** (needed in house by D−45). *Load materials* calls the tech pack's
   `material_requirements` with the order grid:
   Sage 700 × 1.15 × 1.05 = **845.2 m**, Optic White 400 × 1.15 × 1.05 = **483.0 m** → **1,328.2 m** of jersey.
   A separate **trims booking FB/2026/0010** covers 7 trims and packing lines (labels, rib, tape, thread, tags, polybags).
2. *Raise POs* makes one RFQ per vendor for the to-order quantity:
   **P00025** Delta Weave Mills (jersey, USD 3,187.80) and **P00026** Coastal Trims & Labels (USD 425.97).
   Both are confirmed on D−74.
3. Receipt on D−52: the jersey arrives as **10 rolls** (lots R01082…R01091, ~160 m each). Each roll is tagged
   with the booking line, the order, its dye lot, shade band, width and GSM. Trims arrive on D−50. The booking
   moves to **In House** (100 %) and the order's "Fabric in house" tile shows 100 %.
4. **4-point inspection** of every roll (organic buyer requirement): defects are entered by length band,
   and points per 100 sq yd = points × 3600 ÷ (yards × cuttable width"). The worst roll scores 7.1 against the
   accept limit of 40, so **all 10 rolls pass** and their status becomes **Approved**. Only approved rolls can
   be cut.

## 6. Cutting: markers, cut plan, lays, bundles · D−42 to D−39

**Who:** cutting (planner Arjun Pillai; spreaders Sunil / Ravi; cutters Noushad / Deepa).
**Where:** Cutting › Markers, Cut Plans, Lays, Bundles. Screens 46–53.

1. **Markers** for the style: CLO-A (S1 · M2 · L2 · XL1, 83.1 % efficiency), CLO-B (L1 · XL1), and one
   single-size marker per size as a fall-back.
2. **Cut plan per colourway** (extra cut 2 %, 30 pieces per bundle, max 110 plies). *Propose* covers the
   to-cut quantities exactly without over-cutting; *Approve* turns each proposal into a lay:

| Plan | To cut (S/M/L/XL) | Lays |
|---|---|---|
| CP/2026/0007 Sage | 102 / 204 / 255 / 153 | 0011-C01 CLO-A × 102 plies (668.9 m) · 0011-C02 CLO-B × 51 plies (112.9 m) |
| CP/2026/0008 Optic White | 51 / 102 / 153 / 102 | 0011-C03 CLO-A × 51 plies (334.5 m) · 0011-C04 CLO-B × 51 plies (112.9 m) |

3. Each lay is **spread** on approved rolls of its colour (ply numbers run on from roll to roll), then **cut**.
   Cutting checks the rolls (approved, the plan's fabric, enough metres), books **one stock move per roll**
   (1,229 m used; the rest stays as remnants), and posts **cut** to the order: **1,122 pieces** (2 % over).
4. *Create Bundles* splits each lay by size, ratio copy and roll segment at 30 pieces → **56 bundles**
   (B0000194…B0000249). Every bundle gets **12 QR coupons**, one per sewing operation, **672 coupons** in all.
   Each coupon reads `ZG1|bundle|operation|HMAC check`, so retyping a number cannot forge a scan. The bundle ticket
   (screen 53) is printed with tear-off coupons.

## 7. Job work: chest print · D−37 to D−32

**Who:** cutting / line supervisor. **Where:** Job Work › Job Work Orders. Screens 59–60.

1. Job work order **JW/2026/0010**, process **Printing**, vendor **Sunrise Prints**, rate USD 0.18, allowance 1 %,
   all 56 bundles (1,122 pieces). *Send* prints the **delivery challan** and moves the pieces to the
   "Job Work Vendors" location.
2. The panels come back in two lots: D−34 617 good + 2 rejected, D−32 500 good + 3 rejected →
   **1,117 good, 5 rejected**, process loss **0.4 %** (inside the 1 % allowance, no flag).
3. *Bill* raises purchase order **P00027** for the **good pieces only**: 1,117 × 0.18 = **USD 201.06**.

## 8. Sewing floor: line, bulletin, rate card, coupon scans · D−30 to D−27

**Who:** line supervisor (Manoj Kurian), 12 operators (badges OP2101…OP2112).
**Where:** Sewing Floor › Sewing Lines, Operation Bulletins, Coupon Scans; scan station, TV board, daily summary.
Screens 3, 4, 54–58, 80.

1. **Line 5** (12 operators, 14 machines, 480 min/day, target efficiency 60 %) is the work centre on the order.
2. **Bulletin** of ST-0201 is loaded from the tech pack (12 operations, SAM 6.95) and approved. It becomes the
   line's running bulletin: **target 62 pcs/hour** = 12 × 60 × 60 % ÷ 6.95.
3. **Rate card "Line 5 · USD standard minute"**: USD 0.0573 per standard minute (the costing figure), minimum
   USD 9.00 a day, weekly top-up, overtime × 2, a 10 % incentive above 70 % efficiency. *Apply to Bulletins*
   prices each operation (piece rate = SAM × 0.0573).
4. All 56 bundles are **issued** to Line 5. Over **3 days (19–21 Oct)** each operator scans the coupon of the
   operation they run, so there are 672 scans and 7,798 minutes earned. One scan per coupon is enforced: a
   second scan is refused and names who scanned it first. When the last coupon of a bundle is scanned, the
   bundle becomes **sewn** and **sewn** is posted to the order with its good pieces. 6 pieces were rejected
   for an open side seam → **sewn 1,116**. Line efficiency over the three days is
   7,798 ÷ (12 × 3 × 480) ≈ **45 %**, a typical first-week figure on a new style.
5. Sewn bundles are moved to **finished**.

**Quality on the floor** (Quality › Inspections, End-line Check; screens 61, 64): inline D−29 (40 pcs, 3
defects, DHU 7.5), inline D−26 (DHU 2.5), end-line D−24 (120 pcs, DHU 2.5) and D−20 (DHU 0.83). All passed.
DHU = defects × 100 ÷ pieces checked. A repeated defect at the same place on the same line would raise a CAPA
on its own.

## 9. Packing, final inspection, finished stock · D−10 to D−8

**Who:** packing & shipping; quality inspector (Priya Das).
**Where:** Packing & Shipping › Pack Plans, Cartons; Quality › Final Inspections. Screens 63, 66–69.

1. **Pack plan PP/0005**: solid colour / solid size, **25 pcs per carton**, 60 × 40 × 30 cm, 0.19 kg/pc.
   *Generate Cartons* → **44 cartons**. *Pack* gives each one an **SSCC-18** (e.g. 099999990000002410 from the
   demo GS1 prefix) and posts **packed 1,100** to the order (state → **Packed**).
2. **Final inspection QI/2026/00020** (AQL general level II, major 2.5 / minor 4.0): lot 1,100 → code letter **J**,
   sample **80**, major accept 5. Found 5 defects → **Passed**. The order's `final_passed` becomes True. Had
   it failed, the shipment could not leave the factory without a Factory Manager override.
3. *Post to Stock* closes **8 manufacturing orders** (one per variant, exactly the packed pieces), so the
   finished tees are in stock and ready to deliver. (See gap 1 below.)

## 10. Letter of credit, shipment, invoice, payment · D−8 to D

**Who:** packing & shipping, accounts. **Where:** Packing & Shipping › Letters of Credit, Shipments;
Accounting › Customers › Invoices. Screens 70–73, 76.

1. **LC LCCLO71148** (Severn Merchant Bank, Bristol, advised through Coastal Commerce Bank, Kochi): USD 5,600,
   tolerance 5 %, latest shipment D−1, expiry D+20.
2. **Shipment SHP/2026/0005**: sea, Kochi → Felixstowe, Bluewater Logistics, MV Arabian Tern, B/L
   BWL-KOC-90417, FOB. *Add Packed Cartons* (44 cartons, 1,100 pcs), *Confirm*.
3. *Ex-Factory* on D−5 (the planned date, 0 days late). Before the goods leave, the shipment checks five
   things: final inspection passed, LC not expired, inside the latest shipment date, value within LC balance +
   tolerance, and nothing short beyond tolerance. All pass. The system validates the outgoing delivery
   **WH/OUT/00016** (one move per variant), posts **shipped 1,100** to the order and marks the cartons shipped.
4. *Handed Over* → *On Board* → *Documents Presented*: the LC is drawn for the shipment value, **USD 5,445**
   (balance 155).
5. *Create Invoice* → **INV/2026/00009**, USD 5,445.00 (1,100 × 4.95, no tax on export), dated D−3, posted. The
   bank receipt is registered on D ("LCCLO71148 proceeds"), so the invoice is **Paid** and the shipment
   **Paid**.

## 11. Wages · paid for the week of the scans

**Who:** wages clerk. **Where:** Wages › Wage Sheets, Wage Sheet Lines, Rate Cards; wage slip PDF. Screens 77–81.

Wage sheet **WS/2026/0004**, Line 5, week of 19 Oct, rate card "Line 5 · USD standard minute":
*Compute from Scans* claims every unpaid scan of the line in the period (none can be paid twice).

| Operators | Operation-pieces | Piece earnings | Minimum top-up | Overtime | Incentive | **Net payable** |
|---|---|---|---|---|---|---|
| 12 | 13,464 | 467.88 | 20.48 | 6.76 | 7.41 | **502.53** |

Earnings = minutes × 0.0573. Three operators on the shortest operations earned less than 3 × USD 9 and are
topped up to the minimum. The fastest operator (Sreeja V, 86 % efficiency) gets the 10 % incentive, and two
operators have 1.5 h overtime. *Approve* → *Post* writes one balanced journal entry (wages expense / wages
payable, MISC/2026/10/0003), and the scans are locked. *Print Wage Slips* gives one page per operator.

## 12. Order P&L and closing the order · D

**Who:** costing / factory manager. **Where:** Garment Suite › Finance › Order P&L. Screens 74–75.

*Mark Completed* on the production order (allowed because everything has shipped) → state **Completed**. The
P&L **PO/2026/0011 · ST-0201** is refreshed. Finance adds the costs that no other document carries (haulage
and CHA USD 96, GOTS and lab tests USD 150, LC negotiation and courier USD 38.50):

| USD | Planned (cost sheet × 1,100) | Actual | Source of the actual |
|---|---|---|---|
| Material | 3,619.00 | 3,374.19 | fabric cut on the 4 lays (stock valuation) + trims and packing consumed by the MOs |
| Making | 704.00 | 502.53 | wage sheet net pay for the order's scans |
| Job work | — | 201.06 | print PO P00027 |
| Other | 715.00 | 330.50 | the 3 typed costs + PP sample not charged to the buyer (46.00) |
| **Cost** | **5,038.00** | **4,408.28** | variance **−629.72** (under plan) |
| Revenue | | 5,445.00 | posted invoice INV/2026/00009 |
| **Margin** | 7.47 % | **1,036.72 = 19.04 %** | cost USD 4.01 / pc, margin USD 0.94 / pc |

Why the order beat its plan: the markers used 1,229 m against 1,328 m booked (fabric came in under), and piece
rates pay only earned minutes plus a small top-up, while the cost sheet charged 6.95 SAM at 62 % efficiency.
Planned "other" includes the 3 % commercial share and the 0.12 freight (see gap 4).

---

## Gaps this run found (filed in `docs/requests/`)

| # | Where | What happens | Impact |
|---|---|---|---|
| 1 | shipping · *Post to Stock* | The finished-goods MOs consume the BoM fabric **again** (1,331 m, USD 3,194). Cutting already booked it, and the MOs take it from **other orders' rolls, including roll R00703, which is on hold**. | Fabric stock and valuation wrong. **High: fix before the pilot.** |
| 2 | shipping ↔ sales | The shipment delivers and invoices through its own picking and invoice, so the sale order stays "to deliver" (WH/OUT/00015 open) and "to invoice". | Sales and the accountant see an unbilled order. Medium. |
| 3 | shipping · invoice | Shipment invoice lines carry no `garment_order_id` and pick up the default sales tax. The demo sets both by hand. | P&L relies on matching the line name. Small. |
| 4 | P&L | Trims and packing consumed by the MOs are not read. The demo tags those moves with `garment_pnl_order_id`, the documented route. Without that, actual material is about USD 0.39/pc low. Planned "other" also counts freight on an FOB order. | Margin overstated. Medium. |

Files: `docs/requests/zyra_garment_shipping.md` (1–3), `docs/requests/zyra_garment_pnl.md` (4; freight on FOB
belongs to merch's `planned_other_pc`).

## Demo records to open (xml ids in `zyra_garment_suite`)

`story_buyer`, `story_style`, `story_techpack_v1`, `story_sample_fit`, `story_cost_sheet_v1`, `story_cost_sheet`
(v2), `story_sale_order`, `story_order`, `story_labdip_sage`, `story_sample_pp`, `story_booking_fabric`,
`story_booking_trims`, `story_cut_plan_sage`, `story_cut_plan_white`, `story_jobwork_print`, `story_sewing_line`,
`story_rate_card`, `story_pack_plan`, `story_final_inspection`, `story_lc`, `story_shipment`, `story_invoice`,
`story_pnl`.
