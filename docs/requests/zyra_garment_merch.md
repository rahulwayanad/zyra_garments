# Requests to zyra_garment_merch (found by the full-sale demo, 17 Nov 2026)

## 1. Planned "other" cost counts freight on FOB orders (small)
`garment.order.planned_other_pc` adds the cost sheet's `freight_pc` (0.12 on the demo tee) even when the order's
`business_model` / incoterm is FOB, where the buyer pays the freight. The order P&L then shows a planned margin of
7.47 % against the 10 % approved on the cost sheet. Please leave freight out unless the order is sold CIF / CFR.
