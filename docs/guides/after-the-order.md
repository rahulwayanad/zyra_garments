# After the order is confirmed: every stage, and what it does in Odoo

This guide continues `new-buyer-production-order.md` from a **confirmed production order** (PO/2026/00xx) to
cash, wages and the order P&L. For each stage it gives who does it, the clicks, what Odoo records underneath
(stock, purchase, accounting), and what to check. The last section explains where Odoo **manufacturing orders
(MOs)** fit in, and where they don't.

Click-by-click test with a 100-piece order: `docs/testing/test-100-tshirt-sale.md`.
Worked example with real numbers: `.agents/docs/full-sale-walkthrough.md`.

## The one rule behind everything

The **production order** (`garment.order`) is the master record of the job. Floor modules never type quantities on
it. Each one posts **progress** through one API: cutting posts *cut*, sewing *sewn*, packing *packed* and
shipping *shipped*. Every number on the order can be traced to a lay, bundle, carton or shipment
(**Reports › Production Postings**). The order moves by itself:
Confirmed → **In Production** (first piece cut) → **Packed** (packed ≥ ordered) → **Shipped** (shipped ≥ ordered) →
**Completed** (by hand).

```
                 ┌───────────── Merchandising: samples, approvals, T&A ─────────────┐
Production order ┤                                                                  ├─► Completed
                 └► Materials ─► Cutting ─► (Job work) ─► Sewing ─► Quality ─► Packing ─► Shipping ─► Wages / P&L
                    POs, lots     stock out   PO           scans      AQL       MO        delivery,     journal,
                                  per roll                                      (stock)   invoice       report
```

---

## 1. Development: lab dips, trim card, samples, T&A

**Who:** merchandiser. **Where:** Merchandising › Approvals, Samples, Time and Action. Runs alongside materials.

**Approval cards** (lab dip, strike-off, trim card, wash standard). Approvals › New:
1. Kind, style, order, colourway, material. Add **options** A, B, C with a hex colour each. Set the decision due date.
2. Click **Send** (submission 1).
   - If the buyer asks to resubmit, click **Resubmission Asked**, then **Send** again. The submission count goes up.
   - When the buyer accepts, pick the **chosen option** and click **Approved**. Approval is refused until an
     option is chosen, when options exist.
3. The kanban shows overdue cards, and the card counts the days to approval.

**Samples** (proto, fit, size set, PP, TOP, salesman, shipment). Samples › New, with style, order, type, colour,
sizes and the required date:
1. **To Sample Room**, then **Load spec for the size measured** (the graded spec from the tech pack). Type the
   measured values. Each point shows pass or fail against its tolerance.
2. **Send to Buyer** (courier, tracking), then **Approved**, or **Rejected** → **Remake (Next Round)**.
3. Optional: **Invoice Sample Cost** makes a draft customer invoice. A sample not charged to the buyer counts as
   *other cost* on the order P&L.
4. An approved **PP sample** turns the order's PP-sample tile green.

**Time and action.** Milestones were planned back from ex-factory when the order was confirmed. Enter the
**actual date** when each one is done. Each shows On time, Late *n* d or Overdue. The order counts the overdue
ones, and changing ex-factory re-plans the open milestones.

*Odoo underneath:* none of these touch stock. A sample invoice is a normal `account.move` (draft).

## 2. Materials: booking, purchase, rolls, inspection

**Who:** fabric store. **Where:** Materials › Fabric Bookings, Fabric Rolls, Fabric Inspections, Inspection Tablet.

1. **Fabric Bookings › New**: Order, Booking of = **Fabric**. Click **Load from Tech Pack**. Required =
   pieces × consumption × (1 + wastage %), per material and colourway. The "needed in house" date defaults to
   ex-factory − 21 days. Click **Confirm**.
2. Make a second booking with Booking of = **Trims** for labels, rib, thread, tags and polybags.
3. **Raise POs**: one RFQ per vendor for the *to order* quantity (required − in stock − already on open POs).
   Open each and click **Confirm Order** in Purchase.
4. **Receive** in Inventory (the PO's Receipt):
   - **Fabric is lot-tracked: one lot = one roll.** Enter each roll's number and metres.
   - On validation, every roll is tagged with its booking line and order and marked as a fabric roll, status
     **Received**.
   - On the roll, enter the dye lot, shade group, shrinkage group, width and GSM. Relaxation time (24 h by default)
     starts when it is received.
   - Trims are not tracked. A quantity is enough.
5. **4-point inspection** (tablet or form): tap defects by length band (1–4 points). Score = points × 3600 ÷
   (yards × cuttable width in inches). At or under the limit (40), the roll **passes** and is **Approved**. Over
   it, the roll goes on **Hold** with the reason. The inspector can also hold or reject for shade, smell or width,
   with a reason.
6. The booking shows **In House %** and becomes **Short** when the needed date passes without everything in house.
   The order's "Fabric in house" tile reads it.

*Odoo underneath:* `purchase.order` per vendor (lines linked to the booking lines), incoming `stock.picking`, one
`stock.lot` per roll in WH/Stock, valued at the PO price. The vendor bill is made from the PO in Purchase as usual.

✔ Only **Approved** rolls can be cut.

## 3. Cutting: markers, cut plan, lays, bundles

**Who:** cutting master, spreaders, cutters. **Where:** the order's **Propose Cut Plan** button, then
Cutting › Markers, Cut Plans, Lays, Bundles.

1. **Markers** for the style: size ratio (e.g. S1 M2 L2 XL1), length in metres, efficiency %. They can be imported
   from CSV. Keep a single-size marker per size so any quantity can be covered exactly.
2. **Propose Cut Plan** on the order creates **one plan per colourway**. On the plan set the **Extra cut %**,
   **Max plies per lay** and **Pieces per bundle**. To cut = ordered + extra, rounded up.
3. Click **Propose** (or use the lay builder). It picks markers and plies to cover what's left per size without
   over-cutting. Fabric per lay = plies × (marker length + end allowance). Click **Approve Plan**; each proposal
   becomes a **lay**.
4. On each lay, on the **Rolls** tab, list the approved rolls and plies (ply numbers run on from roll to roll;
   mixed shades are flagged). Set table, spreader and cutter. Click **Start Spreading**, then **Confirm Cut**:
   - It checks each roll: approved, the plan's fabric, enough metres.
   - **One stock move per roll** takes the metres used out of WH/Stock (fabric is consumed here, at the cut).
   - It posts **cut** = plies × ratio per size to the order.
5. **Create Bundles**: split by size, ratio copy and roll segment, up to the bundle size. A bundle never mixes
   rolls, so it has one shade. Each bundle gets **one QR coupon per sewing operation** of the tech pack.
   **Print Bundle Tickets** prints them with tear-off coupons.
6. End bits can go back to stock with **Return End Bits**.

*Odoo underneath:* done `stock.move`s of the fabric lots to the production location, valued, and linked to the lay
(the P&L reads them as actual material). No MO is used.

## 4. Job work (outside print, embroidery, wash or sewing)

**Who:** cutting or line supervisor. **Where:** Job Work › Job Work Orders.

1. **New**: process, vendor (must be a job-work vendor), production order, **bundles** (or a typed quantity),
   agreed **rate per piece**, allowed loss % (2 by default), expected date.
2. **Send**: prints the **delivery challan** and moves the pieces to the *Job Work Vendors* location.
3. **Receive** (one or more lots): good and rejected pieces. It can't receive more than is pending. When nothing
   more will come back, **Close Short** writes off what's left as *short*.
4. Process loss = (rejected + short) ÷ sent. The order is flagged when that's above the allowance. It's flagged
   **overdue** after the expected date.
5. **Bill**: creates and confirms a **purchase order** for *good pieces × rate*. The vendor bill follows from that
   PO in Purchase.

*Odoo underneath:* internal `stock.move`s of a generic "Garment Pieces (Job Work)" product (to the vendor and
back), and a `purchase.order` with the Job Work Charge service. The P&L reads it as job-work cost.

## 5. Sewing floor

**Who:** line supervisor, operators. **Where:** Sewing Floor › Operation Bulletins, Line Balancing, Sewing Lines,
Scan Station, Line TV Board, Line Days, Line Planning Board; Wages › Rate Cards.

1. **Bulletin**: New, then **Load from Tech Pack** (operations, sections, machines, SAM; target/hour = 60 ÷ SAM),
   then Approve. Set it as the line's **running bulletin**.
2. **Line balancing** (optional): pitch time, operators per station, bottleneck, balance loss.
   **Apply to Line** sets the line's operators.
3. **Rate card** (Wages): value of a standard minute, minimum daily wage, overtime, incentive.
   **Apply to Bulletins** prices each operation (SAM × minute value).
4. **Issue bundles**: select bundles, **Issue Bundles to Line**. The planning board shows the order on the line by
   week.
5. **Scan Station**: the operator scans their **badge**, then each coupon after doing the operation.
   - It records pieces, minutes earned (pieces × SAM) and earnings.
   - A coupon scans only once; a second scan is refused with who scanned it.
   - If the Wi-Fi drops, scans queue on the device and replay safely.
   - When the last coupon of a bundle is scanned, the bundle is **Sewn** and *sewn* (good pieces) posts to the
     order.
6. **Line TV Board** shows hour-by-hour output against target. **Line Days** shows each day's summary
   (efficiency = earned minutes ÷ (operators × minutes per day), lost minutes, WIP, DHU, downtime). Close the day
   there.
7. Move sewn bundles to **Finished** after finishing and ironing.

*Odoo underneath:* a sewing line is an **`mrp.workcenter`** (Line 1…). Lines are used for capacity and planning
only. No work orders are created, and the scans are Zyra records.

## 6. Quality

**Who:** quality inspector. **Where:** Quality › Inspections, End-line Check, Final Inspections, Corrective Actions.

- **Inline / end-line** inspections: pieces checked and defects (from the library, with position and severity).
  DHU = defects × 100 ÷ pieces. These fail only on a critical defect. The **End-line Check** tablet records by the
  hour.
- **CAPA**: the same defect at the same place on the same line, repeated past the threshold in the window (10 in
  3 days by default), **raises a corrective action by itself**. It moves Open → In progress → Verified → Closed;
  closing needs a root cause, action and owner.
- **Final inspection** (after packing): lot size → AQL code letter and **sample size** (ISO 2859-1, level II,
  major 2.5 / minor 4.0). It fails on any critical, or majors or minors over the accept number.
  - The latest final inspection sets the order's **Final passed** flag. **Shipping cannot leave without it**.
  - A failed lot can be **re-inspected**, or accepted under **concession** by the Factory Manager with a reason.
  - **Print** the final inspection report for the buyer.

*Odoo underneath:* Zyra records only. Odoo CE has no Quality app.

## 7. Packing

**Who:** packing & shipping. **Where:** the order's **Pack Plan** button, Packing & Shipping › Pack Plans, Cartons.

1. **Pack plan**: pack kind **Solid** (one colour and size per carton), **Assorted** (one colour, sizes by ratio)
   or **Ratio** (colours and sizes mixed). Set pieces per carton or the ratio, carton size and weights.
   **Generate More Cartons** creates only the missing ones.
2. **Pack / Scan Cartons**: each carton gets its **SSCC-18** (GS1 prefix in Settings) and posts *packed* to the
   order. Net = pieces × kg/pc, gross = net + empty carton, CBM = L × W × H. Unpacking reverses it.
3. Final inspection (stage 6) is done on the packed lot.
4. **Post to Stock** creates the finished goods: **one MO per variant**, done at once (see *How Odoo MOs fit*
   below).
5. **Packing List** prints per pack plan or per shipment.

## 8. Shipping, invoice and payment

**Who:** shipping, accounts. **Where:** Packing & Shipping › Letters of Credit, Shipments; Accounting.

1. **Letter of credit** (if the buyer pays by LC): amount, tolerance %, latest shipment date, expiry, banks. It
   shows *Expired* after expiry. Amendments go through a wizard and are logged.
2. **Shipment › New**: buyer, orders, mode, ports, forwarder, vessel or flight, B/L, incoterm, LC, planned date.
   Click **Add Packed Cartons**, then **Confirm**.
3. **Ship Ex-factory** checks five rules first. Any failure blocks the shipment unless a **Factory Manager
   overrides** with a reason (logged):
   - final inspection passed;
   - LC not expired;
   - before the LC's latest shipment date;
   - value within the LC balance + tolerance;
   - not short beyond tolerance.

   Then it validates an outgoing **delivery** (one move per variant, out of WH/Stock), posts *shipped* to the
   order and marks the cartons shipped. Days late = actual − planned ex-factory.
4. **Handed Over** → **On Board** → **Documents Presented**. Presenting documents draws the shipment value on the
   LC.
5. **Create Invoice** makes a draft customer invoice (pieces × order price, per order). Post it in Accounting,
   then **Register Payment** when the money arrives. **Mark Paid** on the shipment.

*Odoo underneath:* outgoing `stock.picking` (done) of the finished-goods variants, `account.move` (out_invoice),
`account.payment`. Known gap: the **sale order's own delivery and invoice status stay open**, because the shipment
uses its own documents (`docs/requests/zyra_garment_shipping.md` #2).

## 9. Wages, P&L and closing

**Wages** (wages clerk; Wages › Wage Sheets):
1. **New**: period (a week), sewing line (or empty for the whole floor), rate card, journal and accounts. Click
   **Compute from Scans**:
   - It claims every unpaid scan of the period, grouped per operator.
   - Piece earnings = minutes × minute value; top-up to the minimum (weekly or daily); overtime (typed hours);
     incentive above the efficiency threshold; deductions.
   - **A scan is never paid twice.**
2. **Approve** (lines freeze), then **Post**: one balanced **journal entry** (debit wages expense, credit wages
   payable, per operator). **Print Wage Slips**. The wage payment itself is made from Accounting.
3. **Cancel Posted Sheet** reverses the entry and frees the scans for a corrected sheet.

**Order P&L** (Finance › Order P&L): one per order, refreshed nightly or with **Refresh**.
- Revenue: posted customer invoices less credit notes.
- Planned cost: approved cost sheet × pieces shipped.
- Actual cost:
  - material: fabric cut on lays, plus moves tagged to the order;
  - making: wage net pay, shared by the minutes spent on the order;
  - job work: POs and bills;
  - other: costs typed by finance, plus samples not charged to the buyer.
- It shows margin, margin %, cost variance and cost per piece. Loss orders are red.

**Close the order:** **Mark Completed** (only when everything has shipped). If the order ships short, the Factory
Manager uses **Close Order** (logged).

---

## How Odoo MOs fit in

Odoo's MRP is used for **three things only**: the product and BoM of a style, a gate, and the finished-goods
receipt at packing. **The production order, not an MO, runs the job**, and the floor never uses MO work orders.

```
Tech pack approved ──► product.template (Colour × Size variants) + mrp.bom (code "ST-0101 · v1", techpack_id)
                                                     │
Sale order confirmed ──► garment.order (production order) ── cut / sewn / packed / shipped postings
                                                     │
Pack plan ▸ Post to Stock ──► 1 MO per variant (qty = packed pieces) ──► done at once ──► finished goods in WH/Stock
                                                     │
Shipment ▸ Ship Ex-factory ──► delivery of those finished goods to the buyer
```

**1. Product and BoM (from the tech pack).** Approving a tech pack revision:
- Creates or updates the style's **product template**, with a *Colour* attribute and a *Size (range)* attribute,
  so there is one **variant per colour × size**. Each variant knows its `garment_colour_id` and `garment_size_id`.
- Gives the product the **Manufacture** route, plus **MTO** only if MTO is active (it is archived by default in
  Odoo 18).
- Generates an **`mrp.bom`** (type normal, per 1 piece, `code` = tech pack name, linked by `techpack_id`):
  - one BoM line per tech pack material, with the quantity **including wastage**;
  - colour- or size-specific lines apply only to those variants;
  - **no operations**, so MOs have no work orders.
- Approving a newer revision rewrites its own BoM and **archives the older BoMs**, so Odoo always picks the current
  one.
- See it from the tech pack (BoM button) or Manufacturing › Products › Bills of Materials.

**2. The gate.** Any MO, whether made by hand in Manufacturing, by a replenishment rule or by Zyra:
- is **refused at Confirm** when its style has no approved tech pack;
- is refused when it is linked to a superseded revision (re-link it to the current one);
- with no tech pack set, is linked to the style's current approved revision.

A sale order line for a style without an approved tech pack is refused the same way. The tech pack form has a
**Manufacturing Orders** smart button.

**3. Where MOs are created: Post to Stock only.** On a pack plan, **Post to Stock** takes the packed cartons not yet
posted and, for **each variant**, creates an MO:
- product = the variant; quantity = packed pieces; BoM = the current one; origin = "PP/0005 PO/2026/0011";
- it is confirmed, reserved, produced and **marked done immediately**.

The result:
- **Finished garments enter WH/Stock**, valued, so the shipment's delivery has something to ship.
- The pack plan's **Finished Goods Orders** smart button lists the MOs. They also show in Manufacturing ›
  Manufacturing Orders, and on the tech pack.
- Run it after the final inspection. Each run posts only the new cartons, so it can be done carton batch by
  carton batch.

**4. What the MO consumes, and the known bug.** The MO consumes the **BoM components**:
- **Trims and packing**: correct, because this is where they leave stock. The order P&L does not read these MO
  moves yet (`docs/requests/zyra_garment_pnl.md`).
- **Fabric: wrong.** Fabric already left stock when the lays were cut (stage 3). The MO takes the BoM fabric a
  second time, from whatever rolls are in stock, **even other orders' rolls and rolls on hold**.
  → `docs/requests/zyra_garment_shipping.md` #1, **high, fix before the pilot**. The fix is for the MO to skip
  fabric lines (lot-tracked components).

**5. What not to do.**
- **Keep the MTO route archived.** If MTO were active, confirming a sale order would also create MOs through the
  standard procurement. You would get two sets of MOs, those and the Post to Stock ones, for the same pieces.
- **Don't confirm or produce garment MOs by hand** in Manufacturing for a Zyra order. Progress must come from
  cutting, sewing and packing postings, and stock from Post to Stock.
- **Don't use work orders** for sewing. Sewing lines are work centres for capacity and planning only; output comes
  from coupon scans.

**6. Sale order and stock.** The sale order's own delivery (WH/OUT/…) waits for stock and is never used. The
shipment delivers through its own picking, and once Post to Stock has put finished goods in stock, the old picking
may reserve them. Until shipping request #2 is done, **cancel the sale order's delivery** after the shipment
leaves, and invoice from the shipment, not from the sale order.
