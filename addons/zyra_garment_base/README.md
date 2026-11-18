# zyra_garment_base

Shared base of the Zyra garment ERP (Odoo 18 CE). Every other `zyra_*` garment module depends on it.
**The model, field and xml id names below are a contract**: do not rename them; extend them.

- Depends: `base`, `mail`, `product`, `stock`, `uom`, `hr`, `zyra_garment_theme`
- Version `18.0.1.0.0`, licence OPL-1, application ("Garment" in the app menu)
- All xml ids below are in module `zyra_garment_base` (write `zyra_garment_base.<id>` from other modules).

## Models and fields

### `res.partner` (extended)
| Field | Type | Notes |
|---|---|---|
| `is_garment_buyer` | Boolean | buyer of garment orders |
| `is_jobwork_vendor` | Boolean | vendor for outsourced print / embroidery / wash / sewing |
| `buyer_code` | Char | unique (`buyer_code_unique`) |

### `res.company` (extended) — company figures
| Field | Type | Default | Notes |
|---|---|---|---|
| `minute_value` | Monetary (`currency_id`) | 0.10 | value of one standard minute, company currency |
| `target_efficiency` | Float | 65.0 | **percent** (65.0 = 65 %). Divide by 100 in formulas |
| `working_minutes_per_day` | Integer | 480 | |
| `margin_floor_pct` | Float | 12.0 | percent; cost sheets under it need Factory Manager |
| `garment_week_start` | Selection `'1'`..`'7'` | `'1'` (Monday) | |
| `garment_fabric_accept_points` | Float | 40.0 | 4-point limit (points / 100 sq yd); above → hold (used by materials) |
| `garment_model_fob`, `garment_model_cmt`, `garment_model_own_brand`, `garment_model_mtm`, `garment_model_decoration` | Boolean | FOB, CMT on | business models run (screen 119) |
| `garment_area_merch`, `_materials`, `_cutting`, `_sewing`, `_jobwork`, `_quality`, `_shipping`, `_wages`, `_compliance` | Boolean | all on except compliance | areas shown in the menu (screen 119) |

Helper: `company._garment_making_cost(sam)` = SAM × `minute_value` ÷ (`target_efficiency` / 100).

### `res.config.settings` (extended)
Related, editable: `minute_value`, `target_efficiency`, `working_minutes_per_day`, `margin_floor_pct`,
`garment_week_start`, `garment_fabric_accept_points` (+ `garment_currency_id`). Settings app block
`name="zyra_garment_base"` ("Garment"), button `action_open_garment_setup`.

### Libraries (all with `active`; no `company_id` — shared by all companies, see Decisions)
| Model | Fields |
|---|---|
| `garment.season` | `name`, `code` (unique), `year`, `active` |
| `garment.type` | `name`, `code` (unique), `sequence`, `default_sam`, `active` |
| `garment.size.range` | `name`, `sequence`, `size_ids` (o2m `garment.size`, ordered by sequence), `size_count`, `size_names` (computed "S · M · L"), `active` |
| `garment.size` | `name`, `sequence`, `range_id` (required, cascade); unique (range, name); `_order = range_id, sequence, id` |
| `garment.colour` | `name`, `code`, `pantone`, `hex` (validated `#RRGGBB`), `active` |
| `garment.pom` | `code` (unique), `name`, `sequence`, `garment_category` (`top`/`bottom`/`both`), `how_to_measure`, `default_tolerance` (± cm), `active`. Display `[code] name` |
| `garment.defect` | `code` (unique), `name`, `sequence`, `area` (`fabric`, `stitching`, `seam`, `measurement`, `shade`, `trims`, `print`, `wash`, `finishing`, `packing`), `severity` (`minor`/`major`/`critical`), `department` (`fabric_store`, `cutting`, `sewing`, `jobwork`, `finishing`, `packing`), `active` |
| `garment.machine.type` | `name`, `code` (unique), `sequence`, `stitch_class`, `active` |
| `garment.operation` | `code` (unique), `name`, `sequence`, `type_id` (`garment.type`), `section` (`preparation`, `front`, `back`, `sleeve`, `assembly`, `finishing`), `machine_type_id`, `default_sam`, `active` |

`garment.defect.area` is the *kind* of defect. The place on the garment (collar, left sleeve…) belongs on the
inspection line in `zyra_garment_quality`.

### `stock.lot` (extended) — fabric rolls
A fabric roll is a `stock.lot` with `is_fabric_roll = True`.

| Field | Type | Notes |
|---|---|---|
| `is_fabric_roll` | Boolean | |
| `roll_status` | Selection `received` / `approved` / `hold` / `rejected` | default `received`, tracked, `group_expand` (all four kanban columns) |
| `roll_hold_reason` | Char | reason for hold / reject, tracked |
| `dye_lot`, `shade_group`, `shrinkage_group` | Char | tracked |
| `width_cm`, `gsm` | Float | ≥ 0 |
| `points_per_100sqyd` | Float | written by the 4-point inspection (materials) |

Status methods (buttons on the roll form; callable from code):
- `action_roll_approve()` — from received / hold; clears the reason. **A rejected roll cannot be approved.**
- `action_roll_hold(reason=None)` — from received / approved (not rejected).
- `action_roll_reject(reason=None)`
- `action_roll_reset()` — back to received; releasing a rejected roll needs Factory Manager.
All raise `UserError` on a lot that is not a fabric roll.

### `garment.setup.wizard` (transient) + `garment.setup.wizard.role`
Factory Setup (screen 119): business models, areas in the menu, working time, roles, plus company costing /
fabric figures, size presets and library loading. Button `action_save_setup` (Garment Admin only).
- Area ticks toggle `active` of the section menus. `area_jobwork` toggles
  `zyra_garment_jobwork.menu_garment_jobwork` **if that module defines it** (soft); compliance has no menu.
- Roles: one line per user (`user_id`, `role` ∈ merchandiser, techpack_designer, costing, fabric_store, cutting,
  line_supervisor, quality, packing_shipping, wages, factory_manager, admin); saving adds that group.

### `garment.library` (abstract) — idempotent loaders
- `_load_pom_library()`, `_load_defect_library()` — read `data/library/*.csv`, create missing codes only.
- `_load_size_preset(preset)` with `preset` in `s_xl`, `xs_xxl`, `kids_2_14`; returns the range.
- `_load_demo_libraries()` (demo hook), `_demo_receive_rolls({lot_xmlid: qty})` (demo hook).

Records created by the loaders get xml ids in this module:
- POM: `pom_<code lower>` → `pom_t01` (Chest 1/2) … `pom_t22`, `pom_b01` (Waist 1/2) … `pom_b11` (33 points)
- Defects: `defect_<code lower>` → `defect_f01`…`f08` (fabric), `s01`–`s02` (shade), `c01`–`c03` (cutting),
  `w01`–`w15` (sewing), `m01`–`m02`, `t01`–`t04` (trims), `p01`–`p03`, `d01`–`d05`, `k01`–`k03` (45 defects)
- Size ranges: `size_range_s_xl` (S M L XL), `size_range_xs_xxl` (XS…XXL), `size_range_kids_2_14` (2…14)
- Sizes: `size_<preset>_<size lower>` e.g. `size_s_xl_m`, `size_xs_xxl_xxl`, `size_kids_2_14_8`

These exist after install **with demo**, or after Factory Setup without demo. Use
`env.ref(..., raise_if_not_found=False)` in code; in demo XML they are safe to `ref` (base demo loads them).

## Security
Category `module_category_garment` ("Garment"). Groups (all imply `base.group_user`):

| xml id | Name | Implies |
|---|---|---|
| `group_garment_merchandiser` | Merchandiser | |
| `group_garment_techpack_designer` | Tech Pack Designer | |
| `group_garment_costing` | Costing | |
| `group_garment_fabric_store` | Fabric Store | `stock.group_stock_user` |
| `group_garment_cutting` | Cutting | |
| `group_garment_line_supervisor` | Line Supervisor | |
| `group_garment_quality` | Quality | |
| `group_garment_packing_shipping` | Packing & Shipping | |
| `group_garment_wages` | Wages | |
| `group_garment_factory_manager` | Factory Manager | all nine roles above |
| `group_garment_admin` | Garment Admin | Factory Manager (so everything); `base.user_admin` and `base.user_root` are members |

Access: every internal user reads every library. Write/create/delete: seasons, types, size ranges, sizes,
colours → merchandiser, techpack designer; POMs → techpack designer, quality; defects → quality; operations,
machine types → techpack designer, line supervisor; all → admin (and Factory Manager by implication).
`stock.lot`: fabric store full, cutting and quality read/write; `stock.quant` read for cutting and quality.
Setup wizard: Garment Admin only.

## Menus
| xml id | Name | Parent | Seq |
|---|---|---|---|
| `menu_garment_root` | Garment | — (app; visible to every garment role) | 35 |
| `menu_garment_merch` | Merchandising | root | 20 |
| `menu_garment_materials` | Materials | root | 30 |
| `menu_garment_cutting` | Cutting | root | 40 |
| `menu_garment_sewing` | Sewing Floor | root | 50 |
| *(free: 60 — Job Work section, owned by `zyra_garment_jobwork` as `menu_garment_jobwork`)* | | | |
| `menu_garment_quality` | Quality | root | 70 |
| `menu_garment_shipping` | Packing & Shipping | root | 80 |
| `menu_garment_wages` | Wages | root | 90 |
| `menu_garment_reports` | Reports | root | 100 |
| `menu_garment_config` | Configuration | root | 200 |

Section menus carry no groups; put `groups=` on your own menu items. Empty sections stay hidden until a child
with an action exists. Children defined here:
- `menu_garment_buyers` (Merchandising › Buyers, seq 90), `menu_garment_fabric_rolls` (Materials › Fabric Rolls, seq 50;
  materials may repoint or replace it with the roll board)
- Configuration: `menu_garment_setup` (Factory Setup, admin), `menu_garment_settings` (Settings, admin),
  `menu_garment_config_partners` › `menu_garment_config_buyers`, `menu_garment_config_jobwork_vendors`;
  `menu_garment_config_styles` › `menu_garment_config_seasons`, `_types`, `_size_ranges`, `_colours`, `_poms`;
  `menu_garment_config_floor` › `menu_garment_config_operations`, `_machine_types`, `_defects`.

## Actions and views
Actions: `action_garment_season`, `action_garment_type`, `action_garment_size_range`, `action_garment_colour`,
`action_garment_pom`, `action_garment_defect`, `action_garment_operation`, `action_garment_machine_type`,
`action_garment_buyer`, `action_garment_jobwork_vendor`, `action_garment_fabric_roll`,
`action_garment_setup_wizard`, `action_garment_config_settings`.

Views follow `<model_underscored>_view_list|form|search` (e.g. `garment_pom_view_form`), plus:
`res_partner_view_form_garment` (Garment page), `res_partner_view_search_garment` (filters `garment_buyers`,
`jobwork_vendors`), `res_partner_view_list_garment_buyer`, `stock_lot_view_form_garment` (Fabric Roll page on
the standard lot form), `stock_lot_view_form_garment_roll` / `stock_lot_view_list_garment_roll` /
`stock_lot_view_search_garment_roll` (primary roll views; inherit these for screens 41–42),
`res_config_settings_view_form_garment`, `garment_setup_wizard_view_form`.

## Data files
- `data/garment_machine_type_data.xml` (noupdate): `machine_type_snls`, `_dnls`, `_ol3`, `_ol5`, `_fl`, `_fdoa`,
  `_bh`, `_bs`, `_bt`, `_snap`, `_iron`, `_manual`
- `data/garment_type_data.xml` (noupdate): `garment_type_tshirt`, `_polo`, `_shirt`, `_jean`, `_chino`,
  `_hoodie`, `_shorts`, `_dress`
- `data/garment_operation_data.xml` (noupdate): T-shirt `operation_tee_01`…`operation_tee_12`
  (codes TEE-01…), 5-pocket jean `operation_jean_01`…`operation_jean_24` (codes JEAN-01…)
- `data/library/garment_pom_library.csv`, `garment_defect_library.csv`, `garment_size_presets.csv` — **not**
  in the manifest; loaded by Factory Setup / demo through `garment.library`.

## Demo (`demo/garment_base_demo.xml`)
- Buyers: `partner_buyer_northwind` (NWA), `partner_buyer_bluefin` (BLF), `partner_buyer_maple` (MFR)
- Job-work vendors: `partner_vendor_sunrise_prints` (print), `partner_vendor_kaveri_wash` (wash)
- Fabric supplier: `partner_supplier_delta_weave`
- Seasons: `season_ss27` (SS27), `season_aw26` (AW26)
- Colours: `colour_navy`, `colour_white`, `colour_black`, `colour_grey`, `colour_indigo`, `colour_sky`
- Fabrics (storable, lot-tracked, metres): `product_fabric_jersey` (FAB-SJ-180), `product_fabric_poplin`
  (FAB-POP-SKY), `product_fabric_denim` (FAB-DNM-12)
- Rolls (in WH/Stock): `roll_r00701` received · `roll_r00702` approved · `roll_r00703` hold (46.5 pts) ·
  `roll_r00704` approved (poplin) · `roll_r00705` approved (denim) · `roll_r00706` rejected
- Users: `user_anjali` (Merchandiser), `user_vivek` (Fabric Store), `user_arjun` (Line Supervisor),
  `user_priya` (Quality)
- All POM / defect libraries and the three size presets (xml ids above).

## Tests (`tests/`, tag `zyra`) — 31 tests
Groups imply correctly (FM → nine roles, Admin → FM, fabric store → inventory, ACL by role); company defaults,
settings write the company, making-cost formula; wizard writes company figures, creates size ranges in order,
loads libraries once (idempotent, no duplicate of a hand-entered code), assigns roles, proposes existing
role holders, area tick hides its menu, only Garment Admin can save; roll status changes (approve, hold with
reason, rejected cannot be approved, only FM releases a rejected roll, chatter tracking); master constraints.

## Decisions
- Model names follow the kit (`garment.*`), not the skill's `zyra.garment.*` pattern: the kit is the contract.
- Libraries have no `company_id`: one shared library for all companies, so no multi-company record rules are
  needed here (stock.lot keeps stock's own company rule). Modules with documents add `company_id` + rules.
- `target_efficiency` and `margin_floor_pct` are stored as percentages (65.0), not fractions.
- Factory Manager implies the nine operational roles; Garment Admin implies Factory Manager.
- Fabric Store implies `stock.group_stock_user` so store keepers can receive rolls.
- POM / defect libraries and size presets live in CSV files loaded on demand (wizard / demo), matched by code,
  so loading twice never duplicates. Created records get xml ids (`noupdate`) for other modules' demo.
- `garment.defect.area` means the kind of defect; position on the garment belongs to the inspection.
- Added fields beyond the kit, clearly needed later: `roll_hold_reason` (materials: hold "with the reason"),
  `garment_fabric_accept_points` (materials: "accept limit from company setting"), `garment_week_start`,
  business-model and area flags (screen 119), `garment.operation.type_id/section`, `garment.pom.garment_category`,
  `garment.machine.type.stitch_class`. No shared status mixin: nothing in the kit needed one.
- Screen 119 has four sections; the kit also wants size presets, library loading, minute value and margin floor,
  so they sit in two extra sections below ("Costing and fabric figures", "Size ranges and libraries").
- Menu areas are toggled by archiving the section menu (global, not per company).
- Demo user names on screen 119 (Anjali Menon, Vivek Nair, Arjun Pillai, Priya Das) are reused as demo users.
- There is no `menu_garment_jobwork` here (not in the contract); jobwork creates its own section at seq 60.
- `description` is set in the manifest so Odoo does not parse this README as reStructuredText.
- Licence OPL-1 (skill default for sellable modules) — confirm with Rahul.

## Not done yet
- Nothing from the kit prompt is open. Browser check done for Factory Setup, Fabric Rolls list and Settings
  (headless screenshots); other config lists not visually reviewed.

## Settings switched on at install
- **Lots & Serial Numbers** (`stock.group_production_lot` implied on Internal User, `data/stock_settings_data.xml`):
  fabric rolls are stock lots, so receipts must show the lot column. Odoo's stock demo used to switch it on, so
  databases created without demo (production) could not receive rolls before this.
