# zyra_techpack

Style master and versioned tech packs of the Zyra garment ERP (Odoo 18 CE). A **style** (`garment.style`) holds
the sketch, buyer, colourways and size range; each **tech pack revision** (`zyra.techpack`) holds the bill of
materials per colourway / size, the graded measurement spec, construction details and the operation bulletin.
Approving a revision generates the Odoo BoM; sale and manufacturing orders are gated on an approved tech pack.

- Depends: `zyra_garment_base`, `mrp`, `sale_management`, `sale_mrp` (all Community)
- Version `18.0.2.0.0`, licence OPL-1. Built fresh (no earlier zyra_techpack existed on this machine → no migration).
- **Contract**: `.agents/zyra_build_kit/contracts/wave2_techpack.md` — every name there exists here exactly.

## Models and fields

### `garment.style` (mail.thread, mail.activity.mixin, image.mixin)
| Field | Type | Notes |
|---|---|---|
| `name` | Char, required | |
| `code` | Char, required | unique per company (`code_company_unique`) |
| `buyer_id` | m2o res.partner | domain `is_garment_buyer` |
| `buyer_style_ref`, `collection` | Char | |
| `season_id` | m2o garment.season | |
| `type_id` | m2o garment.type | kanban is grouped by it |
| `fabric_kind` | Selection `woven` / `knit` | |
| `merchandiser_id` | m2o res.users | |
| `size_range_id` | m2o garment.size.range | locked once a revision is approved |
| `size_names` | related | "S · M · L" |
| `colour_ids` | m2m garment.colour | the colourways; `colour_count` |
| `image_1920` (+ `image_128`…) | image.mixin | the sketch |
| `product_tmpl_id` | m2o product.template | the garment; variants = colour × size |
| `variant_count` | Integer | |
| `techpack_ids` | o2m zyra.techpack | `techpack_count` |
| `current_techpack_id` | m2o, computed **stored** | latest **approved** revision |
| `approved_for_production` | Boolean, computed stored | current tech pack exists |
| `stage` | Selection `draft` / `development` / `approved`, stored | statusbar: Draft · In Development · Approved for Production |
| `sam` | Float, stored | SAM of `current_techpack_id` (0 until one is approved) |
| `material_cost` | Monetary | material / pc of current (else working) revision |
| `bom_id` | related `current_techpack_id.bom_id` | |
| `working_techpack_id` | m2o, computed (searchable) | the open revision if any, else current, else latest |
| `working_techpack_state`, `working_revision`, `base_size_id` | related to working revision | |
| `bom_line_ids`, `operation_ids`, `measurement_ids`, `construction_ids`, `measure_unit`, `artwork_note`, `label_note`, `packing_note`, `attachment_ids`, `graded_chart_html` | related to `working_techpack_id` (editable) | the style form tabs edit the open revision |
| `company_id`, `currency_id`, `active`, `notes` | | |

Methods: `action_new_techpack()`, `action_new_version()`, `action_copy_techpack()` (new style + draft v1 copy),
`action_print_techpack()`, `action_generate_variants_bom()`, `action_view_variants()`, `action_view_techpacks()`,
`_ensure_product()` (create/update product template; idempotent), **`_get_variant(colour, size)`** → product.product.

### `zyra.techpack` (one record per revision; mail.thread)
| Field | Type | Notes |
|---|---|---|
| `style_id` | m2o garment.style, required, cascade | |
| `revision` | Integer | 1, 2, … per style, set on create |
| `name` | Char, computed stored | `"ST-0142 · v2"` |
| `state` | Selection `draft`, `submitted`, `approved`, `superseded` | tracked |
| `change_note` | Text | "What changed" |
| `buyer_id` (stored), `type_id` (stored), `season_id`, `size_range_id`, `colour_ids`, `image_1920` | related to style | |
| `base_size_id` | m2o garment.size | must be in the style's range; defaults to the middle size |
| `measure_unit` | Selection `cm` / `inch` | |
| `bom_line_ids` | o2m `zyra.techpack.bom.line` | |
| `measurement_ids` | o2m `zyra.techpack.measurement` | |
| `construction_ids` | o2m `zyra.techpack.construction` | |
| `operation_ids` | o2m `zyra.techpack.operation` | **cutting and sewing read this list** |
| `artwork_note`, `label_note`, `packing_note` | Html | |
| `attachment_ids` | m2m ir.attachment | Documents tab |
| `sam` | Float, stored | Σ `operation_ids.sam` |
| `material_cost` | Monetary, stored | material per piece with wastage, dearest colourway |
| `graded_chart_html` | Html (computed) | graded size chart, base size bold and marked `*` |
| `bom_id` | m2o mrp.bom | generated on approval |
| `sale_line_ids` | o2m sale.order.line | `sale_order_count` |
| `production_ids` | o2m mrp.production | `production_count` |
| `submitted_date`, `approved_date`, `approved_user_id` | | |
| `company_id` (related style, stored), `currency_id` | | |

Methods:
- `action_submit()` draft → submitted (designer, merchandiser, FM). Needs ≥ 1 material; base size if there is a measurement spec.
- `action_approve()` submitted → approved (**Factory Manager only**); previous approved revision → `superseded`; generates the BoM.
- `action_reset_draft()` submitted → draft (designer, FM).
- `action_new_revision()` copies this revision into the next draft (refused while another revision is open).
- `action_print()`, `action_view_sale_orders()`, `action_view_productions()`, `action_view_bom()`.
- **`material_requirements(qty_by_variant)`** — `qty_by_variant = {(colour_id, size_id): qty}` (ids or records).
  Returns a list of dicts `{product_id, colour_id, uom_id, qty_net, qty_with_wastage}` (ids; plus
  `material_kind`, `price_unit`), one per material **and colourway**. `qty_net = Σ qty × consumption`,
  `qty_with_wastage = qty_net × (1 + wastage_pct/100)`. A line with empty colour applies to every colourway, a line
  with empty size to every size.
- **`get_graded_chart()`** → `{pom_id: {size_id: value}}`; value = base + (size steps from `base_size_id`) × `grade_rule`.
- `_generate_bom()`, `_material_cost_by_colour()` → `{colour_id: cost/pc}`, `_get_sizes()`, `_copy_to_style(style)`.
- `_LOCKED_FIELDS`: spec fields frozen once approved/superseded. **Fields other modules add (e.g. a planned cost)
  can still be written on an approved revision.** Context `techpack_unlock=True` bypasses the lock (code only).

### Lines (all locked when the revision is approved/superseded; `sequence` on each)
- `zyra.techpack.bom.line`: `product_id` (material), `material_kind` (`fabric`, `trim`, `packing`), `placement`,
  `colour_id` (empty = all colourways, must be a style colourway), `size_id` (empty = all sizes, must be in range),
  `consumption` (per piece, in `uom_id`), `uom_id` (same category as product unit), `wastage_pct` (3.0 = 3 %),
  `price_unit` (defaults to product cost), `currency_id`, `qty_with_wastage`, `cost_per_piece` (= qty with wastage × price).
- `zyra.techpack.measurement`: `pom_id` (unique per revision), `pom_code`, `base_value`, `tol_plus`, `tol_minus`
  (default from POM), `grade_rule`.
- `zyra.techpack.construction`: `area`, `stitch_class` (Selection ISO 101/301/401/406/504/514/516/602/605, bartack,
  buttonhole), `spi`, `seam_type` (superimposed, lapped, bound, flat, edge_finish, ornamental), `seam_allowance`, `note`.
- `zyra.techpack.operation`: `operation_id` (garment.operation), `name`, `section`, `machine_type_id`, `sam`
  (all four default from the operation library).

### Standard models extended
| Model | Fields / behaviour |
|---|---|
| `product.template` | `garment_style_id` |
| `product.product` | `garment_colour_id`, `garment_size_id` (stored, from the variant's attribute values) |
| `product.attribute` | `garment_role` (`colour`/`size`), `garment_size_range_id` — one "Colour" attribute, one "Size (range)" attribute per size range |
| `product.attribute.value` | `garment_colour_id`, `garment_size_id` |
| `mrp.bom` | `techpack_id` |
| `mrp.production` | `garment_style_id` (stored related), `techpack_id` (defaults to the style's current); **gate**: `action_confirm` refuses an MO whose style has no approved tech pack, or whose `techpack_id` is not approved (superseded) |
| `sale.order` / `sale.order.line` | `garment_style_id`, `techpack_id` (set at confirmation); **gate**: `action_confirm` refuses lines for styles without an approved tech pack; `_prepare_procurement_values` passes `techpack_id` |
| `stock.move` | `techpack_id`; passed on through `_prepare_procurement_values` |
| `stock.rule` | `_get_custom_move_fields` + `techpack_id`; `_get_matching_bom` uses the tech pack's BoM; `_prepare_mo_vals` writes `techpack_id` on generated MOs |

## Security
Groups from `zyra_garment_base`. Every internal user reads styles, tech packs and lines (sales users need it for the
gate). Merchandiser: create/write styles, read tech packs, **submit** (through sudo after the group check), New
Version. Tech Pack Designer: full on styles, tech packs and lines (not approve). Factory Manager: full + **approve**.
Readers may comment in chatter (`_mail_post_access = 'read'`). Record rules: multi-company on `garment.style` and
`zyra.techpack` (lines follow their tech pack).

## Menus, actions, views, report
- Menus: `menu_garment_styles` (Merchandising › Styles, seq 10), `menu_zyra_techpack` (Merchandising › Tech Packs, seq 20)
  under `zyra_garment_base.menu_garment_merch`.
- Actions: `action_garment_style` (kanban, list, form), `action_zyra_techpack` (list, form; default filter "Not Superseded").
- Views: `garment_style_view_kanban|list|form|search`, `zyra_techpack_view_list|form|search`,
  `zyra_techpack_bom_line_view_list`, `zyra_techpack_operation_view_list`, `zyra_techpack_measurement_view_list`,
  `zyra_techpack_construction_view_list`, `product_template_form_view_garment_style`, `mrp_bom_form_view_techpack`,
  `view_order_form_techpack`, `mrp_production_form_view_techpack`, `mrp_production_tree_view_techpack`.
- Extension points for merch / costing on the style form: `<div name="style_kpis">` (KPI tiles `kpi_variants`,
  `kpi_sam`, `kpi_material`, `kpi_techpack`, `kpi_approval`), `<div name="button_box">`, groups `style` and
  `colours_sizes`, notebook pages `materials`, `operations`, `measurements`, `construction`, `artwork`, `labels`,
  `packing`, `versions`, `documents`. Tech pack form: `techpack_kpis`, `button_box`.
- Report: **`zyra_techpack.action_report_techpack`** (qweb-pdf on `zyra.techpack`, template
  `zyra_techpack.report_techpack`) — header, sketch, BOM, graded spec with base size marked, construction, operation
  bulletin with total SAM (screen 37). "Tech Pack PDF" on the style prints the working revision.

## Screens
22 Style cards (kanban by garment type: code, status pill, buyer, type · colourways · SAM, merchandiser avatar) ·
23 Style form (statusbar, buttons Generate Variants & BoM / New Version / Copy Tech Pack / Tech Pack PDF, KPI tiles,
Style + Colours and Sizes sections, tabs) · 24 Measurement spec with graded chart, base size bold · 25 Construction ·
37 printed tech pack. Order/sample/approval/costed-FOB tiles of screen 23 are added by merch / costing.

## Demo (`demo/zyra_techpack_demo.xml` + `models/techpack_demo.py`)
Materials `product_fabric_twill`, `product_fabric_pocketing`, `product_trim_*` (neck rib, neck tape, thread, main
label, care label, hangtag, shank button, rivet, zip, shirt button, interlining), `product_pack_polybag`,
`product_pack_carton`. Styles and revisions:

| Style xml id | Code | Buyer | Revisions |
|---|---|---|---|
| `style_crew_tee` | ST-0101 Crew Neck Tee (3 colourways, S–XL, TEE-01…12) | Northwind | `techpack_crew_tee_v1` approved, **`techpack_crew_tee_v2` draft** |
| `style_chino` | ST-0102 Five-pocket Chino (2 colourways, JEAN-01…24) | Bluefin | `techpack_chino_v1` superseded, `techpack_chino_v2` approved |
| `style_jean` | ST-0103 Straight Leg Jean (indigo) | Maple | `techpack_jean_v1` approved |
| `style_polo` | ST-0104 Classic Pique Polo (XS–XXL, base XL) | Maple | `techpack_polo_v1` approved |
| `style_oxford` | ST-0105 Oxford Button-down Shirt | Northwind | `techpack_oxford_v1` submitted (in development) |

Approved styles have products `product_tmpl_crew_tee`, `product_tmpl_chino`, `product_tmpl_jean`, `product_tmpl_polo`
(variants colour × size) and generated BoMs.

## Tests (`tests/`, tag `zyra`) — 38 tests
Revisions (v1 naming, one open revision, new version copies lines, old stays approved until new approved, approved is
locked, only FM approves, merchandiser submits but cannot edit, submit needs materials, reset to draft, style stage,
style SAM, library defaults, style form edits open revision, copy tech pack, colourway check, cost with wastage,
report renders); grading (formula, base change regrades, base marked, base in range) and material requirements
(per colourway with wastage, all-colour lines, size lines); variants/BoM (colour × size, idempotent, new colourway,
BoM per colourway/size with wastage, new revision archives old BoM); gates (SO blocked/allowed + tech pack recorded,
non-garment SO, MO blocked/allowed, MO on superseded tech pack, SO → MTO → MO carries tech pack and its BoM).

## Decisions
- Built fresh (no existing module, no data) → no migration, no "12 existing tests"; own suite instead.
- `price_unit` and `cost_per_piece` on BOM lines are **Float** (digits "Product Price" / 4), not Monetary: Odoo's
  Monetary rounds to the currency's 2 decimals, which breaks trims costing fractions of a cent. Read them the same way.
- `material_kind` keeps exactly the contract values (`fabric`, `trim`, `packing`); labels and thread are trims.
- `material_requirements` aggregates per material **and order colourway** (all-colour trims are split per colourway).
- BoM quantities include wastage; colour/size-specific lines use `bom_product_template_attribute_value_ids`.
  A new approved revision archives the earlier BoMs of the style so `_bom_find` returns the current one.
- One "Colour" product attribute shared by all styles; one "Size (range name)" attribute per size range, so every
  size value maps to exactly one `garment.size`.
- `current_techpack_id` = latest **approved** (superseded never counts). Style `sam` is 0 until a revision is approved.
- The style form tabs show/edit the *working* revision (open draft if any, else current approved), read-only unless
  it is a draft.
- SO line `techpack_id` is set at confirmation (the revision in force then). An MO linked to a superseded revision is
  refused until it is re-linked (no silent spec change).
- Products created for styles get the Manufacture route, and MTO only if that route is active (MTO is archived by
  default in Odoo 18; activating it is a warehouse decision).
- Material / pc of a style = dearest colourway (conservative for costing).
- Approval/submission run with sudo after an explicit group check, so merchandisers can submit without line rights.

## Not done yet
- Tech pack sketches are simple SVG line drawings; artwork placement images rely on the Documents tab.
- No inch ↔ cm conversion: `measure_unit` only labels the values.
- PDF rendering not checked on this machine (no wkhtmltopdf); the HTML report was rendered and reviewed.
