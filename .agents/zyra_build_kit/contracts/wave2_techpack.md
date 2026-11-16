# Wave 2 contract — what zyra_techpack provides (T2 builds it; T3 costing and T4 merch build on it in parallel)

T2 must implement these names exactly; T3/T4 code against them before T2 is merged. Anything extra is free.

## garment.style (owned by zyra_techpack)
The style master. `_inherit = ['mail.thread', 'mail.activity.mixin']`.
- `name` (Char, required) — style name, e.g. "Five-pocket Chino"
- `code` (Char, required, unique per company) — e.g. "ST-0142"
- `buyer_id` (m2o res.partner, domain is_garment_buyer), `season_id` (garment.season), `type_id` (garment.type)
- `size_range_id` (garment.size.range), `colour_ids` (m2m garment.colour) — the colourways
- `image_1920` (image.mixin) — the sketch
- `product_tmpl_id` (m2o product.template) — the garment product; variants = colour × size
- `sam` (Float) — standard allowed minutes per piece (from the current tech pack's operations)
- `techpack_ids` (o2m zyra.techpack), `current_techpack_id` (m2o, computed: latest approved revision)
- `approved_for_production` (Boolean, computed: current tech pack approved)
- `company_id`, `active`
Views: kanban "Style cards" (screen 22) + form (screen 23) + list. T4 (merch) inherits the form/kanban to add
order figures (open orders, pieces, price left after material); T3 may add cost fields. T2 puts menus under
`zyra_garment_base.menu_garment_merch`.

## zyra.techpack (one record per revision)
- `style_id` (m2o garment.style, required), `revision` (Integer, 1, 2, …), `name` (computed "ST-0142 · v2")
- `state` Selection: `draft`, `submitted`, `approved`, `superseded` (old approved stays approved until the new one
  is approved; one open revision per style)
- `bom_line_ids` → `zyra.techpack.bom.line`: `product_id` (material, product.product), `material_kind`
  Selection (`fabric`, `trim`, `packing`), `colour_id` (garment.colour, empty = all colourways), `size_id`
  (garment.size, empty = all sizes), `consumption` (Float, per piece, in `uom_id`), `uom_id`, `wastage_pct`
  (Float, percent: 3.0 = 3 %), `price_unit` (Monetary, `currency_id`)
- `measurement_ids` → `zyra.techpack.measurement`: `pom_id` (garment.pom), `base_value`, `tol_plus`, `tol_minus`,
  `grade_rule` (increment per size step); graded values per size via `get_graded_chart()` →
  `{pom_id: {size_id: value}}`; base size = `base_size_id` on zyra.techpack (screen 24)
- `construction_ids` → `zyra.techpack.construction`: `area`, `stitch_class`, `spi`, `seam_type`,
  `seam_allowance` (screen 25)
- `operation_ids` → `zyra.techpack.operation`: `sequence`, `operation_id` (garment.operation), `section`,
  `machine_type_id`, `sam` — **cutting (bundle coupons) and sewing (bulletin) read this list**
- `sam` (Float, computed = sum of operation_ids.sam)
- `bom_id` (m2o mrp.bom, generated on approval), links to `sale.order` / `mrp.production` as in the kit
- Method `material_requirements(qty_by_variant)` → list of dicts
  `{product_id, colour_id, uom_id, qty_net, qty_with_wastage}` for a dict `{(colour_id, size_id): qty}`.
  Materials (wave 3) uses this for fabric bookings.
- Printed tech pack report: xml id `zyra_techpack.action_report_techpack` (screen 37)

## Groups
Use `zyra_garment_base.group_garment_techpack_designer` (edit), merchandiser (read + submit), factory_manager
(approve).
