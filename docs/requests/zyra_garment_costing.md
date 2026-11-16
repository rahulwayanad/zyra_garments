# Request from zyra_garment_merch to zyra_garment_costing

zyra_garment_merch reads the cost sheet **softly** (no dependency). Please keep these names, or tell merch if they change:

- Model `garment.cost.sheet`; approved sheets have `state == 'approved'`; link field `techpack_id` (or `style_id`).
- Per-piece figures read for the production order's "Planned cost per piece" section (screens 34–36) and the
  "Planned margin" KPI tile (screen 2): `material_cost_pc`, `making_cost_pc`, other cost = sum of
  `process_cost_pc`, `overhead_amount_pc`, `commission_amount_pc`, `freight_pc` (whichever exist), `margin_pct`.
- Style "Costed FOB" tile (screen 23): `fob_price` of the latest approved sheet of the style.
- Style "Price less material" (screen 23) uses `garment.style.costed_fob_price` (costing's field, read with sudo)
  when it is set. Merch's own "Costed FOB" tile (`kpi_costed_fob`) hides itself when costing is installed, so
  costing's `kpi_costed_fob_*` tiles are the only ones shown. Please keep the name `costed_fob_price`.
- Costing's `production_order_ref` search on `garment.order` by `techpack_id` / `style_id` / `buyer_id` matches
  merch's field names.
