# zyra_garment_costing

Versioned garment cost sheets for the Zyra garment ERP (Odoo 18 CE): material per colourway from the tech pack
BoM, trims, processes, making cost from SAM, shares of the FOB price, FOB / CIF price, margin against the company
margin floor, Factory Manager approval below the floor, quotation from the approved sheet.
**The model, field and xml id names below are a contract** for merch, P&L, cockpit and portal.

- Depends: `zyra_techpack`, `purchase`, `sale` (through zyra_techpack: `zyra_garment_base`, theme, mrp, sale_management)
- Version `18.0.1.0.0`, licence OPL-1. All xml ids are in module `zyra_garment_costing`.

## Formulas (each is a model method, tested with known numbers)
| Figure | Formula | Method on `garment.cost.sheet` |
|---|---|---|
| Material cost / pc (line) | consumption × (1 + wastage % / 100) × price × share % / 100 | `_formula_material_cost_pc` |
| Process cost / pc | per piece: cost; for the whole order: cost ÷ quantity basis | `_formula_process_cost_pc` |
| Making cost / pc | SAM × cost per minute ÷ (line efficiency % / 100) | `_formula_making_cost` |
| Cost / pc | fabric + trims + processes + making (fabric = 0 if the buyer supplies it) | `_cost_parts()["total"]` |
| FOB price | cost ÷ (1 − (commercial and finance % + commission % + margin %) / 100) | `_formula_fob_price` |
| Margin at a price | 100 − commercial % − commission % − cost ÷ price × 100 | `_formula_margin_at_price` |
| CIF price | FOB + freight / pc | |
| Quoted value | FOB (rounded to currency) × quantity basis | |
| Material share % | (fabric + trims) ÷ FOB × 100 | |
| Below floor | margin % < margin floor % (company `margin_floor_pct`, copied on the sheet when costed) | |

Overheads (commercial and finance), commission and margin are **shares of the FOB price**, so the cost is grossed
up, not marked up. Defaults: cost per minute = company `minute_value`, line efficiency = company
`target_efficiency` (both percent-stored figures are divided by 100 in formulas), margin floor = company
`margin_floor_pct`. `_cost_parts(**overrides)` returns the unrounded build-up
`{fabric, trims, processes, making, total, fob}`; stored per-piece subtotals are Monetary (2 decimals) but the FOB
is always computed from unrounded line costs.

## Models

### `garment.cost.sheet` (mail.thread, mail.activity.mixin) — screens 31, 32
| Field | Type | Notes |
|---|---|---|
| `name` | Char | sheet number `CS/2026/0008` (sequence `garment.cost.sheet`), shared by every version of the sheet |
| `version` | Integer | 1, 2, …; `display_name` = `CS/2026/0008 · ST-0126 · v1` |
| `is_latest` | Boolean, computed + searchable | latest version of its number (filter "Latest versions", default) |
| `state` | Selection | `draft`, `submitted` ("Awaiting Approval"), `approved`, `rejected`, `superseded` |
| `techpack_id` | m2o `zyra.techpack`, required | the tech pack revision costed |
| `style_id` | m2o `garment.style` | related, stored; `style_label` = "[ST-0104] Classic Pique Polo" |
| `buyer_id` | m2o res.partner | defaults to the style's buyer |
| `production_order_ref` | Char, computed | soft: names of `garment.order` of the style/tech pack when merch is installed |
| `quantity_basis` | Integer | pieces quoted; per-order costs are spread over it |
| `buyer_supplies_fabric` | Boolean | CMT: fabric left out of the price |
| `costing_date`, `user_id` (Costed By) | | |
| `material_line_ids` | o2m `garment.cost.sheet.material` | all material lines; `fabric_line_ids` / `trim_line_ids` are the same lines filtered by kind |
| `process_line_ids` | o2m `garment.cost.sheet.process` | |
| `sam`, `line_efficiency` (%), `cost_per_minute` | Float | defaults from tech pack / company |
| `overhead_pct` ("Commercial and Finance %"), `commission_pct`, `margin_pct`, `freight_pc` | | shares of FOB; freight for CIF |
| `margin_floor_pct`, `below_floor` | Float, Boolean (stored) | |
| `fabric_cost_pc`, `trim_cost_pc`, `material_cost_pc` (= fabric + trims), `process_cost_pc`, `making_cost_pc`, `total_cost_pc` | Monetary, stored | per piece |
| `overhead_amount_pc`, `commission_amount_pc`, `margin_amount_pc` | Monetary, stored | per piece |
| `target_price`, `fob_price`, `fob_over_target`, `cif_price`, `quoted_value`, `material_share_pct` | stored | |
| `approved_by_id`, `approved_date`, `floor_override_reason` | | written on approval |
| `sale_order_ids` | m2m sale.order | quotations made from the sheet |
| `version_ids` | o2m (computed) | all versions of the same number |

Methods / buttons: `action_submit`, `action_approve` (opens the reason wizard when below the floor),
`_do_approve(reason=None)`, `action_reject`, `action_reset_draft`, `action_new_version`, `action_what_if`,
`action_load_from_techpack`, `action_create_quotation`, `action_print`.

### `garment.cost.sheet.material`
`sheet_id`, `sequence`, `material_kind` (`fabric`/`trim`/`packing`), `method` (`techpack` = loaded from the BoM and
replaced on reload, `manual`), `product_id`, `colour_id`, `consumption`, `uom_id`, `wastage_pct`, `price_unit`
(4 decimals), `share_pct` (share of the order, 100 = every piece), `cost_pc` (stored, 4 decimals).

### `garment.cost.sheet.process`
`sheet_id`, `process_type` (`print`, `embroidery`, `wash`, `jobwork`, `testing`, `packing`, `other`), `name`,
`partner_id` (Done By), `charge_basis` (`piece` / `order`), `cost`, `cost_pc`.

### Wizards
- `garment.cost.sheet.approve.wizard` — reason for approval below the floor (Factory Manager).
- `garment.cost.sheet.whatif` — try SAM, efficiency, cost per minute and margin; shows FOB, against target, margin
  at the target price; "Use Margin at Target", "Apply to Sheet" (draft only).

### Added to `zyra.techpack` (fields visible to merchandiser, costing, tech pack designer)
`cost_sheet_ids`, `cost_sheet_count`, **`approved_cost_sheet_id`** (written on approval; moves to the newer
approved version of the same sheet), stored related: **`planned_material_cost`**, `planned_making_cost`,
**`planned_cost_per_piece`** (= `total_cost_pc`), **`planned_fob_price`**, `planned_margin_pct`, `planned_currency_id`.

### Added to `garment.style` (computed, same groups)
`approved_cost_sheet_id` (current tech pack's approved sheet, else the style's latest approved sheet),
`costed_fob_price`, `costed_below_floor`.

**What merch prices from:** `style.approved_cost_sheet_id` (or `techpack.approved_cost_sheet_id`) → `fob_price`,
`material_cost_pc`, `total_cost_pc`, `quantity_basis`, `buyer_id`. Soft-read with `'garment.cost.sheet' in env`.

## Rules (tests name them)
- Approve: Costing or Factory Manager. A sheet with margin under the floor: **Factory Manager only, with a reason**,
  posted in chatter ("Approved below the margin floor (4.5% against 12.0%): …") and kept in `floor_override_reason`.
- Approving a version supersedes the version approved before it (same number); the old version stays approved
  until then. New Version only from the latest version, and only when it is approved or rejected.
- Approved / superseded sheets cannot change or be deleted.
- Shares of FOB (commercial + commission + margin) must stay under 100 %; efficiency > 0; quantity ≥ 1.
- A new sheet loads its materials from the tech pack BoM: one line per (material, colourway); size-specific lines
  are averaged; a colourway line gets an equal share (100 ÷ colourways), an all-colourway line 100 %. Price = BoM
  price, else first vendor price, else product cost.

## Security
Read/write/create/delete: merchandiser, costing, factory manager, admin; read: tech pack designer. Approve
wizard: costing, FM. What If: merchandiser, costing, FM. Multi-company record rules on the three models.

## Menus, views, report
- Menu `menu_garment_cost_sheets` (Merchandising › Cost Sheets, seq 30), action `action_garment_cost_sheet`.
- Views `garment_cost_sheet_view_list|form|search`, `zyra_techpack_view_form_costing` (Cost Sheets smart button,
  "Planned FOB" tile), `garment_style_view_form_costing` ("Costed FOB" tile on screen 23, red below the floor).
- Report `action_report_cost_sheet` (template `report_cost_sheet`) — screen 38.

## Demo (`demo/garment_costing_demo.xml` → `models/costing_demo.py`)
On the zyra_techpack demo styles: `cost_sheet_tee_v1` (approved) + `cost_sheet_tee_v2` (draft);
`cost_sheet_polo_v1` (**approved below the floor by the Factory Manager with a reason** — screen 32);
`cost_sheet_chino_v1` (superseded) + `cost_sheet_chino_v2` (approved, on tech pack v2);
`cost_sheet_jean_v1` (awaiting approval, under floor); `cost_sheet_polo_bluefin_v1` (rejected);
`cost_sheet_oxford_v1` (draft). Costed by Anjali Menon.

## Tests (`tests/`, tag `zyra`) — 29 tests
Every formula with known numbers, company defaults (percent efficiency ÷ 100), tech pack loading (shares, size
average), totals, CMT fabric, floor flag, share limit, What If; workflow: sequence, costing approves above floor,
merchandiser cannot approve, below floor needs FM, reason kept in chatter, no reason refused, planned cost on the
tech pack and style, approved sheet locked, new version supersedes old, new version only from latest, reject /
reset, reload keeps manual lines, quotation price and quantity, report renders, cost fields hidden from floor roles.

## Decisions
- Kit says depends `zyra_techpack, purchase`; `sale` added for "Create Quotation" (already pulled in by techpack).
  `purchase` is used for the vendor price fallback on materials.
- Extra state `rejected` (screen 31 shows a red "Re…" status); statusbar shows Draft / Awaiting Approval / Approved
  as on screen 32.
- Overheads, commission and margin are shares of the FOB (gross-up), matching the domain skill formula
  FOB = cost ÷ (1 − margin %) extended to all three shares.
- The margin floor is copied onto the sheet when it is created, so changing the company floor later does not
  re-colour old sheets.
- Screen 31 shows no KPI tiles; the kit's "KPI header" is the tile row of the form (screen 32). The image wins.
- Production order column: there is no hard dependency on merch, so it is a computed text that lists the style's
  `garment.order` records when merch is installed (empty otherwise; demo shows it empty here).
- Create Quotation makes one line for the style's first garment variant at FOB × quantity basis (the size/colour
  grid belongs to merch's production order). Generates the style's product if it has none yet.
- Material lines are loaded automatically on create and on "Load from Tech Pack" (draft only); manual lines stay.
- Cost fields added to techpack / style carry `groups=` so floor roles (cutting, sewing, quality) can still open
  tech packs without access to cost sheets.
- Screen 23's style form gets the "Costed FOB" tile only (no extra smart button, to match the image).
- Demo uses cost per minute 0.0573 and line efficiency 62 % (screen 32), not the company defaults.

## Not done yet
- Fabric "Method" only distinguishes tech pack / manual (no marker-based consumption method).
- Production order link becomes a real many2one only if merch later depends on costing (or a bridge module).
