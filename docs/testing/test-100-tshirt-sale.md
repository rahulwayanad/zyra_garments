# Test script: sell 100 T-shirts to a buyer, start to finish

This script takes one small order through every Zyra module in the web client, with a check (✔) after each step.

- **Database:** one with the Zyra demo loaded (e.g. `garments`). Log in as **admin**, who holds every garment role.
- **What is sold:** 100 Navy **Crew Neck Tees** (style **ST-0101**) to the demo buyer **Northwind**, sizes M 50 and
  L 50. The style already has an approved tech pack and an approved cost sheet, so the test starts at the sale
  order. Two sizes keep the hand scanning to about 24 coupons.
- **Menus:** every path below starts at the **Garment Suite** app unless it names another app.
- **Worked example with real numbers:** PO/2026/0011 in `.agents/docs/full-sale-walkthrough.md`.

Record each result as Pass or Fail with a note.

---

## 1. Sale order → production order

| # | Do this | Check |
|---|---|---|
| 1.1 | Open **Merchandising › Styles › ST-0101 Crew Neck Tee**. | ✔ Status **Approved for Production**. Note the **Costed FOB** tile; it is the price to use. |
| 1.2 | **Sales › Orders › New**. Customer **Northwind**, Customer Reference `TEST-100`. Add two lines: *Crew Neck Tee (Navy, M)* qty 50 and *Crew Neck Tee (Navy, L)* qty 50, both at the FOB price. | ✔ Total = 100 × FOB (plus any default tax). |
| 1.3 | Click **Confirm**. | ✔ A **Production Orders** smart button appears. |
| 1.4 | Open the production order **PO/2026/00xx**. | ✔ State **Confirmed**, buyer PO `TEST-100`, grid Navy M 50 / L 50 (100 pcs), price = FOB, T&A milestones filled in. |
| 1.5 | Set **Ex-factory** about 3 weeks ahead and **Sewing Line** = *Line 1*. Save. | ✔ T&A planned dates move with the ex-factory date (logged in the chatter). |

## 2. Materials

| # | Do this | Check |
|---|---|---|
| 2.1 | **Materials › Fabric Bookings › New**. Order = your PO, Booking of = **Fabric**. Click **Load from Tech Pack**, then **Confirm**. | ✔ One line: single jersey, Navy, about **121.9 m** (100 × 1.15 m × 1.06 wastage). |
| 2.2 | Click **Raise POs**. Open the RFQ (Delta Weave Mills) and click **Confirm Order**. | ✔ The booking's Purchase Orders button shows 1 PO. |
| 2.3 | On the PO's **Receipt**, enter 125 m with lot `TEST-R1`, then **Validate**. | ✔ Booking **In House 100 %**. Roll **TEST-R1** shows on **Materials › Fabric Rolls** as *Received*. |
| 2.4 | **Materials › Inspection Tablet**: pick roll TEST-R1, tap 2–3 small defects, then **Finish**. (Or use Fabric Inspections › New.) | ✔ Result **Pass**, roll status **Approved**. |
| 2.5 | *Negative test:* tap many 4-point defects on a second roll. | ✔ Result **Hold** with the reason "4-point score … over the accept limit 40". A held roll cannot be cut. |

## 3. Cutting

| # | Do this | Check |
|---|---|---|
| 3.1 | On the production order, click **Propose Cut Plan**. Open the Navy plan and set **Extra Cut %** = 0 and **Pieces per Bundle** = 50. Click **Propose**. | ✔ Proposed lays use the single-size markers **TS-M** × 50 plies and **TS-L** × 50 plies, with no over-cut. |
| 3.2 | Click **Approve Plan**. | ✔ Two lays are created in state Planned. |
| 3.3 | Open each lay. On the **Rolls** tab add TEST-R1 with all the plies. Click **Start Spreading**, then **Confirm Cut**. | ✔ The order shows **Cut 100**, state **In Production**. Roll TEST-R1 has fewer metres on hand. |
| 3.4 | *Negative test:* try to cut a lay on a roll that is on hold or rejected. | ✔ Refused with a message naming the roll. |
| 3.5 | Click **Create Bundles** on each lay. | ✔ **2 bundles of 50**, each with **12 coupons** (one per sewing operation). |
| 3.6 | Click **Print Bundle Tickets**. | ✔ Ticket with one tear-off QR coupon per operation. |

## 4. Job work: chest print (optional)

| # | Do this | Check |
|---|---|---|
| 4.1 | **Job Work › Job Work Orders › New**. Process **Printing**, vendor **Sunrise Prints**, Production Order = yours, Bundles = both bundles, Rate 0.18. | ✔ Qty sent = 100. |
| 4.2 | Click **Send**. | ✔ Delivery challan prints. The pieces move to the *Job Work Vendors* location. |
| 4.3 | Click **Receive**: 99 good, 1 rejected. | ✔ State **Received**, process loss **1 %**. |
| 4.4 | Click **Bill**. | ✔ Purchase order for **99 × 0.18** (good pieces only). State **Billed**. |

## 5. Sewing

| # | Do this | Check |
|---|---|---|
| 5.1 | Select both bundles (**Cutting › Bundles**) and click **Issue Bundles to Line** → Line 1. | ✔ Bundle stage **Issued**, line Line 1. |
| 5.2 | Open **Sewing Floor › Scan Station**. Scan or type an operator badge (OP1018, OP1019 …), then scan or paste a coupon **payload** (on the bundle form, Coupons tab). Repeat for all 24 coupons, spread over a few operators. | ✔ Each scan shows the operator, operation, pieces and minutes earned. |
| 5.3 | *Negative test:* scan the same coupon again. | ✔ Refused, and the message names who scanned it first. |
| 5.4 | Scan the last coupon of a bundle. | ✔ Bundle becomes **Sewn**. The order's **Sewn** count goes up by 50. |
| 5.5 | Open **Sewing Floor › Line TV Board** and **Line Days** for Line 1. | ✔ Today's output, target and efficiency show your scans. |

## 6. Quality on the line

| # | Do this | Check |
|---|---|---|
| 6.1 | **Quality › Inspections › New**: kind Inline, Order = yours, 20 pieces checked, 1 defect. Click **Complete**. | ✔ DHU **5.0**, result **Passed**. |
| 6.2 | **Quality › End-line Check** (tablet): tap a few defects. | ✔ Hourly pieces, defects and DHU update. |

## 7. Packing and final inspection

| # | Do this | Check |
|---|---|---|
| 7.1 | On the production order, click **Pack Plan**. Pack Kind **Solid**, 25 pieces per carton, carton 60 × 40 × 30 cm. Click **Generate More Cartons**. | ✔ **4 cartons** planned (M 2, L 2). |
| 7.2 | Click **Pack / Scan Cartons** and pack all four. | ✔ Each carton has an **SSCC-18** number. The order shows **Packed 100**, state **Packed**. |
| 7.3 | **Quality › Final Inspections › New**: Order = yours, Lot size 100. | ✔ Code letter **F**, sample size **20**. |
| 7.4 | Enter 1 minor defect, then click **Complete**. | ✔ Result **Passed**. The order's Final inspection tile is green. |
| 7.5 | *Negative test (on a copy, or before 7.4):* complete a final inspection with a **critical** defect. | ✔ Result **Failed**. The shipment in 8.2 cannot leave without a Factory Manager override with a reason. |
| 7.6 | On the pack plan, click **Post to Stock**. | ✔ **2 manufacturing orders** done (Navy M 50, Navy L 50). |

## 8. Shipping, invoice and payment

| # | Do this | Check |
|---|---|---|
| 8.1 | *(Optional)* **Packing & Shipping › Letters of Credit › New**: buyer Northwind, amount a little above the order value, latest shipment date and expiry in the future, state Open. | ✔ Balance = amount. |
| 8.2 | **Packing & Shipping › Shipments › New**: buyer Northwind, Order = yours, planned date today, mode Sea, port Kochi (and the LC, if made). Click **Add Packed Cartons**, then **Confirm**, then **Ship Ex-factory**. | ✔ 4 cartons, 100 pcs. A delivery is validated. The order shows **Shipped 100**, state **Shipped**. |
| 8.3 | Click **Handed Over**, then **On Board**, then **Documents Presented**. | ✔ If an LC is linked, it is drawn for the shipment value. |
| 8.4 | Click **Create Invoice**, then post the invoice. | ✔ One line: 100 × order price. |
| 8.5 | On the invoice click **Register Payment**. Then on the shipment click **Mark Paid**. | ✔ Invoice **Paid**, shipment stage **Paid**. |

## 9. Wages, P&L and closing

| # | Do this | Check |
|---|---|---|
| 9.1 | **Wages › Wage Sheets › New**: Line 1, this week, the active rate card. Click **Compute from Scans**. | ✔ One row per operator who scanned. Pieces and minutes match the scans. Operators under the minimum get a top-up. |
| 9.2 | Click **Compute from Scans** again on a new sheet for the same week. | ✔ Your scans are not paid twice. |
| 9.3 | On the first sheet click **Approve**, then **Post**. | ✔ State **Posted**, and a balanced journal entry is created. **Print Wage Slips** prints one page per operator. |
| 9.4 | On the production order click **Mark Completed**. | ✔ State **Completed**. |
| 9.5 | **Finance › Order P&L**: open your order and click **Refresh**. | ✔ Revenue = the invoice. Actual cost has material (fabric cut on the lays), making (the wage sheet), job work (the print PO) and other. Margin against the cost sheet's planned margin. |

---

## Known gaps (do not log these as new bugs)

Filed in `docs/requests/`:

1. After step 8, sale order `TEST-100` still says **To Deliver** and **To Invoice**. Shipping delivers and invoices
   through its own documents (`zyra_garment_shipping.md` #2).
2. Step 7.6 consumes the BoM fabric a **second time**, from other rolls in stock (`zyra_garment_shipping.md` #1, high).
3. The order P&L does not count the trims consumed by the MOs, so actual material is low (`zyra_garment_pnl.md`).
4. Planned "other" cost on the P&L includes freight even on FOB orders (`zyra_garment_merch.md`).
5. If a screen shows *time zone "Asia/Calcutta" not recognized*, set the user's time zone to Asia/Kolkata (Settings ›
   Users), or install `tzdata-legacy` on the server and restart PostgreSQL.
