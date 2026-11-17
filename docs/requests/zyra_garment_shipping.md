# Requests to zyra_garment_shipping (found by the full-sale demo, 17 Nov 2026)

Found while running one order end to end (`zyra_garment_suite` demo, order of style ST-0201). Walkthrough:
`.agents/docs/full-sale-walkthrough.md`.

## 1. "Post to Stock" consumes fabric a second time (bug, high)
`garment.pack.plan._garment_produce` makes one MO per variant with the style's BoM, so the MO consumes the
BoM fabric (1.15 m × 1.05 per piece) although cutting already consumed the real fabric when the lays were cut
(`garment.lay.action_cut`). In the demo, 1,100 packed tees took **1,331 m more jersey** (USD 3,194 of stock
value) out of stock — from **other orders' rolls**, including roll R00703, which is **on hold** after a failed
4-point inspection.
Expected: the finished-goods MO consumes only what was not issued before (trims, packing), or no fabric at all
(skip `material_kind == 'fabric'` BoM lines / lot-tracked components), and never a roll that is not approved.

## 2. Sale order stays "to deliver" / "to invoice" (gap, medium)
When the production order comes from a sale order (merch), the shipment validates its own outgoing picking and
creates its own invoice. The sale order's own delivery (WH/OUT/…) stays open and its invoice status stays
"To Invoice" forever, so Sales shows the order as undelivered and unbilled.
Options: ship through the sale order's picking (`garment.order.sale_order_id.picking_ids`) and invoice from the
sale order lines, or link the shipment invoice lines to `sale_line_ids` and cancel the duplicate picking.

## 3. Shipment invoice lines are not tagged with the order (small)
`action_create_invoice` writes no `garment_order_id` on the lines; P&L falls back to matching the line name.
Please set `garment_order_id` (field added by zyra_garment_pnl — soft write when the field exists) and no
default sales tax on export lines.
