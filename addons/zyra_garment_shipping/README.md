# zyra_garment_shipping — Packing & Shipping

Pack plans, cartons with SSCC-18 labels, shipments that ship through stock pickings, letters of credit and
the printed packing list. Screens 67–73 and 76.

Depends: `zyra_garment_merch`, `zyra_garment_theme`, `stock`, `account`, `mrp`.
Soft dependency: `zyra_garment_quality` (reads `garment.order.final_passed` only if the field exists).

## Models

| Model | What it is |
|---|---|
| `garment.pack.plan` | Pack plan per production order: pack kind (`solid` = solid colour/solid size, `assorted` = solid colour/assorted sizes, `ratio` = ratio pack mixing colours), ratio lines, pieces per carton, carton size and weights, cartons planned / packed / shipped, gross kg, CBM. *Generate More Cartons* creates only the missing ones. *Post to Stock* makes one MO per variant for exactly the packed pieces. |
| `garment.pack.plan.ratio` | Ratio line: (colour for ratio packs), size, pieces. |
| `garment.carton` | Carton: number, content by colour × size (`garment.carton.line`), pieces, net/gross kg, CBM, SSCC-18, state planned → packed → shipped, shipment. Packing calls `garment.order._garment_add_progress('packed', …)`; unpacking reverses it. |
| `garment.shipment` | Buyer, orders, mode, ports, forwarder, planned/actual ex-factory, days late, cartons, pieces, weights, CBM, value, LC, stage (draft → confirmed → ex-factory → handed over → on board → documents presented → paid). Ex-factory validates one outgoing `stock.picking` (one move per variant) and posts `shipped` to the orders. |
| `garment.lc` / `garment.lc.drawing` | Letter of credit: amount, tolerance %, drawn, balance, latest shipment date, expiry, days left, state (draft/open/closed; shown as *Expired* past expiry), drawings, amendments (wizard, logged). |
| Wizards | `garment.carton.pack.wizard` (pack N cartons), `garment.shipment.override.wizard` (manager override with reason), `garment.lc.amend.wizard`. |

## Rules (tests name them)
- SSCC-18 = extension digit + company GS1 prefix (7–10 digits) + serial + GS1 mod-10 check digit; unique;
  scanning `(00)` + SSCC finds the carton. Default prefix is a fake demo prefix (set yours in Settings).
- Carton maths: net = pieces × net kg/pc; gross = net + empty carton; CBM = L × W × H / 1,000,000.
- Days late = actual (or today while not shipped) − planned ex-factory, when positive.
- LC balance = amount − drawings; drawings may not exceed amount + tolerance; *Documents Presented* draws the
  shipment value.
- A shipment cannot leave the factory while: final inspection not passed (quality), LC expired, shipped after
  the LC latest shipment date, value above LC balance + tolerance, or a final shipment short beyond
  tolerance. Only a Factory Manager can override, with a reason; it is logged in the chatter.

## Menus
Packing & Shipping: Pack Plans, Cartons, Shipments, Letters of Credit (under the base section menu).
Settings: GS1 company prefix and SSCC extension digit. Order form: *Pack Plan* button and carton counts.

## What other modules can rely on
- `garment.order.pack_plan_ids`, `shipment_ids`, `garment_cartons_planned`, `garment_cartons_packed`.
- `garment.order._garment_shipping_final_ok()` → bool (quality hook point).
- `garment.shipment.stage`, `value`, `actual_date`, `days_late`, `picking_ids`, `invoice_ids`
  (`action_create_invoice` bills shipped pieces at the order price).
- `garment.lc.balance`, `drawn`, `days_left`.
- Reports: printed packing list for a shipment or a pack plan.

## Decisions
- Quality is not merged yet: `final_passed` is read only when the field exists; otherwise quality never blocks.
- Finished goods: *Post to Stock* closes one MO per variant; finished moves are not pre-picked (mrp would
  count them as already produced and post nothing).
- A shipment of orders without product variants ships without a stock picking and says so in the chatter.
- Demo data runs from `garment.shipping.demo._load_demo` on the merch demo orders; the demo admin is put in the
  Factory Manager group so the demo override can be recorded.

## Not done yet
- Screens were matched in the first session; a final side-by-side pass against s067–s073 and s076 in a
  browser is still to do.
