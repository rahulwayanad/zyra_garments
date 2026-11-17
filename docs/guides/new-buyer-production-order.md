# How to set up a production order for a new buyer

This guide takes a buyer who is not yet in the system to a **confirmed production order**: buyer → style →
tech pack → cost sheet → order. From there the floor work (fabric, cutting, sewing, quality, packing, shipping)
follows `docs/testing/test-100-tshirt-sale.md`, from section 2.

- **Who does what:** the merchandiser does most steps. The **Factory Manager** must approve the tech pack, and must
  approve a cost sheet whose margin is under the floor (12 % by default). Admin holds every role.
- **Menus:** paths start at the **Garment Suite** app unless they name another app.
- **Example used below:** buyer *Harbour & Pine* (code HNP) orders a crew-neck tee in Navy and White, sizes S–XL.

---

## Step 1 · Create the buyer

**Merchandising › Buyers › New**

| Field | Example | Note |
|---|---|---|
| Name | Harbour & Pine Ltd | Company, address, country, e-mail as usual |
| **Garment Buyer** (Garment tab) | ✔ ticked | Without it the buyer is not offered on styles and orders |
| **Buyer Code** | HNP | Short and unique; the system refuses a duplicate |

Save.

## Step 2 · Check the libraries (once per factory)

**Configuration** (Garment Suite › Configuration). Most of these already exist. Only add what is missing:

- **Colours:** name, code, Pantone, hex (e.g. *Navy* `#1F2A44`). Each colourway on a style must exist here.
- **Size Ranges:** e.g. *S–XL* (S · M · L · XL). Factory Setup can load the presets S–XL, XS–XXL and Kids 2–14.
- **Seasons**, **Garment Types** (T-shirt, polo …), **Operations** (TEE-01…12 for a T-shirt with their SAM),
  **Points of Measure**.

## Step 3 · Create the style

**Merchandising › Styles › New**

| Field | Example |
|---|---|
| Code | ST-0301 (unique in the company) |
| Name | Harbour Crew Tee |
| Buyer | Harbour & Pine Ltd |
| Buyer style ref | HP-T-118 |
| Season / Collection | SS27 / Core |
| Garment type | T-shirt |
| Fabric kind | Knit |
| Size range | S–XL (it is locked once a tech pack is approved) |
| Colourways | Navy, White |
| Merchandiser | the person responsible |
| Image | the sketch (optional) |

Save, then click **Create Tech Pack**. This creates **ST-0301 · v1** in Draft.

## Step 4 · Fill in and approve the tech pack

Open the tech pack (Merchandising › Tech Packs, or the style's smart button). Set the **Base size** (usually M).

| Tab | What to enter | Why it matters |
|---|---|---|
| **Materials** | One line per material: product (e.g. single jersey 180 gsm), kind (fabric / trim / packing), colourway (empty = every colourway), size (empty = every size), consumption per piece, unit, wastage %. Fabric needs a line for **each** colourway. | Drives the fabric booking quantities, the BoM and the cost sheet |
| **Operation Bulletins** | Add the operations (e.g. TEE-01 … TEE-12). SAM comes from the library and can be edited. | Total SAM drives making cost, line target and the bundle coupons (1 coupon per operation) |
| **Measurement Spec** | Points of measure with base value, tolerances and grade rule. The graded chart shows below the table. | Samples are measured against it |
| Construction, Artwork, Labels, Packing | Seams, stitches, print placement, label and packing notes | Printed on the tech pack PDF |

Then:
1. **Submit** (merchandiser or designer). It needs at least one material, and a base size when there is a
   measurement spec.
2. **Approve** (**Factory Manager only**).

✔ The style changes to **Approved for Production**. The system creates the **product variants** (colour × size)
and the **Odoo BoM**. SAM and material cost show on the style.

> Without an approved tech pack, **no sale order or production order can be confirmed** for the style.

## Step 5 · Cost sheet and price (recommended)

Skip this step and the order has no planned cost, no margin tile and no planned figures on the P&L.

**Merchandising › Cost Sheets › New**: Tech pack = ST-0301 · v1, Buyer, Quantity basis (e.g. 1,000), Target price.
The materials load from the tech pack by themselves.

1. Add **processes** if any (print, wash, testing, packing), per piece or per order.
2. Check **SAM**, **Cost per minute**, **Line efficiency %**, **Commercial & finance %** and **Margin %**. The FOB is
   worked out as cost ÷ (1 − those shares).
3. Use **What If** to try other margins or efficiencies against the target price.
4. Click **Send for Approval**, then **Approve**.
   - Costing can approve when the margin is at or above the floor.
   - Under the floor (red), only the **Factory Manager** can approve, and must give a reason. The reason is kept on
     the sheet.
5. Optional: **Create Quotation** makes a sale quotation at the FOB price, to send to the buyer.

If the buyer negotiates, click **New Version** on the approved sheet, change the margin and approve again. The
older version becomes superseded.

## Step 6 · Create the production order

Choose one of the two ways.

### Way A: from a sale order (recommended)
**Sales › Orders › New** (or open the quotation from step 5).
1. Customer = the buyer. **Customer Reference** = the buyer's PO number.
2. One line per variant, e.g. *Harbour Crew Tee (Navy, M)* qty 200, at the FOB price.
3. Set the **Delivery date** if known. Click **Confirm**.

✔ A **production order** is created and confirmed by itself: grid from the lines, price = average price, buyer
PO = customer reference, T&A template *Bulk order – 8 weeks* applied. Open it from the **Production Orders**
smart button.

### Way B: directly
**Merchandising › Production Orders › New**
1. **Buyer**, **Style** (the approved tech pack revision fills in by itself), **Buyer PO**, **Business model**
   (FOB / CMT), **Merchandiser**.
2. **Colourways** and **Sizes** default to the style's. Remove any colourway not ordered.
3. Enter the pieces in the **Size & Colour grid** (e.g. Navy: S 100, M 200, L 200, XL 100).
4. **Price per piece** (the FOB from the cost sheet), **Order date**, **Ex-factory date**, **Sewing line**,
   **T&A template**.
5. Click **Confirm Order**. It is refused while the grid is empty or the style is not approved.

### Check after either way
- ✔ State **Confirmed**, number **PO/2026/00xx**, order value = price × pieces.
- ✔ **Time and Action** milestones are planned back from the ex-factory date.
- ✔ The planned cost section and margin tile show figures when a cost sheet was approved.
- To change quantities after confirming, click **Amend Order**, edit the grid, then **Done Amending**. The grid is
  locked otherwise.

## Step 7 · What follows

Every stage below, with the clicks, what Odoo records underneath and how Odoo MOs fit in, is explained in
**`docs/guides/after-the-order.md`**.

| Next | Where | Test script section |
|---|---|---|
| Lab dip, trim card, PP sample | Merchandising › Approvals / Samples | — |
| Fabric and trims booking, POs, rolls, 4-point inspection | Materials | 2 |
| Cut plan, lays, bundles and coupons | *Propose Cut Plan* on the order, Cutting | 3 |
| Print / wash / embroidery outside | Job Work | 4 |
| Issue bundles to the line, coupon scans | Sewing Floor | 5 |
| Inline, end-line and final AQL inspection | Quality | 6, 7 |
| Pack plan, cartons, shipment, invoice | Packing & Shipping | 7, 8 |
| Wage sheet, order P&L, Mark Completed | Wages, Finance | 9 |

## Common stops

| Message or symptom | Fix |
|---|---|
| Buyer not offered on the style or order | Tick **Garment Buyer** on the partner (step 1) |
| "Style … is not approved for production" | Submit the tech pack, and have the Factory Manager approve it (step 4) |
| Sale order confirm refused for the style | Same as above |
| "Enter the quantities in the size and colour grid" | Fill in the grid before **Confirm Order** |
| No variant offered on the sale order | Approve the tech pack, or click **Generate Variants & BoM** on the style |
| Cost sheet approve opens a reason box | Margin is under the floor; a Factory Manager must approve with a reason |
| Grid cannot be edited | The order is confirmed; use **Amend Order** |
| *time zone "Asia/Calcutta" not recognized* | Set the user's time zone to Asia/Kolkata (Settings › Users) |
