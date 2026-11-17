# Requests to zyra_garment_pnl (found by the full-sale demo, 17 Nov 2026)

## 1. Trims and packing consumed by the finished-goods MO are not counted (gap, medium)
`_src_material` reads fabric cut on lays and moves tagged `garment_pnl_order_id`. Trims and packing are consumed
by shipping's "Post to Stock" MOs, which nobody tags, so the P&L understates material by the trims cost
(USD 0.39 / piece on the demo tee). The demo tags those MO moves itself. Please read the raw moves of
`garment.order.pack_plan_ids.production_ids` (excluding lot-tracked fabric, already counted on the lays) — see
also shipping request 1.
