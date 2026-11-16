# zyra_garment_merch

Merchandising for the Zyra garment ERP (Odoo 18 CE): **production orders** with the size × colour grid and the
**progress API** every floor module posts to, **samples** with fit measurements, buyer **approval cards**, and the
**time-and-action** plan. It also adds the order figures to the style (owned by `zyra_techpack`).

- Depends: `zyra_garment_base`, `zyra_garment_theme`, `zyra_techpack`, `sale_management`, `sale_mrp`
- Soft link (read only if installed, never a dependency): `zyra_garment_costing` (`garment.cost.sheet`)
- Version `18.0.1.0.0`, licence OPL-1. Screens: 2, 22–23 (inherited), 26–30, 33–36.

## Progress API — the contract for waves 3–4

Cutting, sewing, quality, packing and shipping **never write quantities on the order themselves**. They call:

```python
posting = order._garment_add_progress(stage, colour_id, size_id, qty, ref=None, date=None)
```

| Argument | Type | Meaning |
|---|---|---|
| `self` | one `garment.order` | `ensure_one()` |
| `stage` | str | `'cut'`, `'sewn'`, `'packed'` or `'shipped'` |
| `colour_id` | int or `garment.colour` record | colourway of the grid cell |
| `size_id` | int or `garment.size` record | size of the grid cell |
| `qty` | int (a float with no decimals is accepted) | pieces to add; **negative reverses** an earlier posting |
| `ref` | str, optional | your document: bundle, lay, carton, shipment no. Shown in the postings list |
| `date` | datetime, optional | when it happened (default now) |

**Returns** the new `garment.order.progress` record (one posting).

**Validation (raises, nothing is written):**
| Case | Exception |
|---|---|
| `stage` not one of the four | `ValidationError` |
| `qty` is 0, a bool, a string, or a float with decimals | `ValidationError` |
| order state not in `confirmed`, `in_production`, `packed`, `shipped` (draft, closed, cancelled refuse) | `UserError` |
| no grid cell for (`colour_id`, `size_id`) on this order | `UserError` |
| the posting would make the cell's stage total negative | `ValidationError` |

Over-production is allowed (cut 5,388 against 5,396 ordered is normal), and stages are independent (no rule that
sewn ≤ cut: modules post in their own rhythm).

**Rights:** the posting is written with `sudo()` after the call, so any internal user who can read the order may
post (cutting, line supervisor, quality, packing roles have no write right on the order). `user_id` on the posting
is the real caller.

**Side effects:** the cell's `qty_<stage>` and the order totals update (stored computes). The order state advances by
itself: `confirmed → in_production` on the first cut/sewn/packed piece; `→ packed` when packed ≥ ordered;
`→ shipped` when shipped ≥ ordered. It never goes back by itself.

Read helper: `order._garment_get_grid()` → `{(colour_id, size_id): {'ordered', 'cut', 'sewn', 'packed', 'shipped'}}`.

## Models

### `garment.order` — Production Order (`mail.thread`, sequence `PO/%(year)s/0001`)
| Field | Type | Notes |
|---|---|---|
| `name` | Char | order no. |
| `state` | Selection | `draft`, `confirmed`, `in_production`, `packed`, `shipped`, `closed` (label "Completed"), `cancel` |
| `sale_order_id` | m2o `sale.order` | set when opened from a sale order |
| `buyer_id` | m2o `res.partner` (buyer) | required |
| `buyer_po` | Char | buyer PO no. |
| `business_model` | Selection `fob` / `cmt` | |
| `merchandiser_id` | m2o `res.users` | |
| `style_id` | m2o `garment.style` | required |
| `techpack_id` | m2o `zyra.techpack` | revision in force (defaults to the style's current approved one) |
| `colour_ids`, `size_ids` | m2m | axes of the grid (default: style colourways and size range) |
| `date_order`, `ex_factory_date` | Date | ex-factory ≥ order date |
| `days_to_ex_factory` | Integer (computed, not stored) | negative = past |
| `is_late` | Boolean (computed, searchable) | ex-factory passed, state open, `qty_shipped < qty_ordered` |
| `sewing_line_id` | m2o `mrp.workcenter` | sewing lines are work centres (architecture) |
| `line_ids` | o2m `garment.order.line` | the grid |
| `qty_ordered`, `qty_cut`, `qty_sewn`, `qty_packed`, `qty_shipped`, `qty_balance` | Integer (stored) | totals; balance = ordered − shipped |
| `packed_pct` | Float (stored) | packed ÷ ordered × 100 |
| `price_unit`, `order_value` | Monetary | value = price × ordered |
| `planned_material_pc`, `planned_making_pc`, `planned_other_pc`, `planned_margin_pct`, `cost_sheet_ref`, `has_cost_sheet`, `planned_margin_low` | computed | from the approved `garment.cost.sheet` when costing is installed |
| `sample_ids`, `sample_count`, `pp_sample_status`, `pp_sample_ok` | | latest PP sample status |
| `tna_template_id`, `milestone_ids`, `milestone_count`, `milestone_done_count`, `milestone_overdue_count` | | |
| `progress_ids`, `posting_count` | | postings |
| `is_amending` | Boolean | set by Amend Order |

Buttons / methods: `action_confirm` (needs pieces in the grid and `style_id.approved_for_production`; applies the
T&A template), `action_start_production`, `action_mark_completed` (needs everything shipped), `action_close`
(Factory Manager; closes short, logged), `action_amend` / `action_done_amending`, `action_cancel`,
`action_draft`, `action_apply_tna_template`. The grid (`line_ids`) of a non-draft order can only change while
amending. Ex-factory changes reschedule the open template milestones and log it.

### `garment.order.line` — grid cell
`order_id`, `colour_id`, `size_id` (unique per order; size must be in the style's range), `colour_hex`,
`size_sequence`, `product_id` (variant when opened from a sale order), `qty_ordered`, computed stored
`qty_cut`, `qty_sewn`, `qty_packed`, `qty_shipped`, `qty_balance` (sums of the postings).

### `garment.order.progress` — posting
`order_id`, `line_id`, `colour_id`, `size_id`, `stage`, `qty`, `date`, `user_id`, `ref`. Read-only after creation
(`write` raises; post a correction).

### `garment.sample` (`mail.thread`, `SMP/%(year)s/0001`)
`state`: `requested`, `in_progress` ("In the Sample Room"), `rejected` ("Rejected, Remake Due"), `with_buyer`,
`approved` (kanban columns via `group_expand`). `sample_type`: `proto`, `fit`, `size_set`, `pp`, `top`,
`salesman`, `shipment`. Fields: `style_id`, `order_id`, `buyer_id`, `colour_id`, `size_ids`, `size_measured_id`,
`pieces`, `request_date`, `required_date`, `sent_date`, `decision_date`, `round`, `courier`, `tracking_ref`, `cost`,
`charge_to_buyer`, `invoice_id`, `buyer_comments`, `measurement_ids`, `round_ids`, `points_measured`,
`points_out`, `is_overdue` (searchable). Methods: `action_start`, `action_send_to_buyer`, `action_approve`,
`action_reject`, `action_remake` (round + 1), `action_load_spec` (graded spec of the size measured from the tech
pack, via `zyra.techpack.get_graded_chart()`), `action_invoice_cost` (draft customer invoice, once).

`garment.sample.measurement`: `round`, `pom_id`, `size_id`, `spec`, `tol_plus`, `tol_minus`, `measured`,
`deviation` (= measured − spec), `result` (`pending` when nothing measured, `pass`, `fail`).
`garment.sample.round`: one line per buyer decision (round, dates, decision, points, comments).

### `garment.approval` (`mail.thread`, `APR/%(year)s/0001`)
`kind`: `lab_dip`, `strike_off`, `trim_card`, `wash_standard`. `state`: `draft` ("To Send"), `resubmit`,
`with_buyer`, `approved`. Fields: `style_id`, `order_id`, `colour_id`, `material_id`, `buyer_id`,
`merchandiser_id`, `option_ids` (`garment.approval.option`: `name`, `hex`, `note`), `chosen_option_id`,
`options_sent` ("A, B and C against Lilac"), `swatch_html`, `swatch_image`, `submission`, `first_sent_date`,
`sent_date`, `decision_due`, `decision_date`, `courier`, `buyer_comment`, KPI computes `decision_due_label`,
`days_to_approval`, `other_open_count`, `is_overdue`. Methods: `action_send` (submission + 1),
`action_approve` (needs the chosen option when options exist), `action_ask_resubmission`.

### `garment.tna.template` / `garment.tna.template.line` / `garment.tna.milestone`
Template lines: `name`, `sequence`, `days_before_ex_factory`, `owner_id`. Milestone: `order_id`, `name`,
`planned_date` (= ex-factory − days), `actual_date`, `owner_id` (template owner or the merchandiser),
`status` (`pending`, `on_time`, `late`, `overdue`; searchable), `delay_days`, `status_label` ("Late 1 d"),
`action_mark_done`. Data: `tna_template_bulk` "Bulk order – 8 weeks" (11 milestones, 53 days → 0).

### `garment.style` (inherited from `zyra_techpack`)
`garment_order_ids`, `order_count`, `open_order_count`, `pieces_on_order`, `sample_count`, `samples_pending`,
`approval_count`, `approvals_pending`, `costed_fob`, `price_less_material` (= costed FOB − `material_cost`),
`action_view_garment_orders`, `action_view_samples`, `action_view_approvals`.

### `sale.order` (inherited)
Confirming a sale order opens **one production order per garment style** on it (variants → grid cells via
`product.product.garment_colour_id/garment_size_id`), confirmed, with the bulk T&A template, `buyer_po` =
customer reference, price = average price per piece. `garment_order_ids`, `garment_order_count`, smart button.

## Views, actions, menus
| xml id | What |
|---|---|
| `action_garment_order` | Production Orders (list = screen 33, late in red; form = screens 2, 34–36) |
| `action_garment_sample` | Samples (kanban = screen 26, form = 27–28) |
| `action_garment_approval` | Approvals (kanban = 29, form = 30) |
| `action_garment_tna_milestone` | Time and Action (list, calendar) |
| `action_garment_tna_template` | T&A Templates |
| `action_garment_order_progress` | Production Postings |
| Reports | `action_report_order_breakdown` (screen 35 printed), `action_report_sample_ticket`, `action_report_sample_fit`, `action_report_approval_card` |

Menus under `zyra_garment_base.menu_garment_merch`: `menu_garment_orders` (30), `menu_garment_samples` (40),
`menu_garment_approvals` (50), `menu_garment_tna` (60). Reports › `menu_garment_order_postings`. Configuration ›
`menu_garment_config_merch` › `menu_garment_config_tna_templates`.

**Extension points for other modules** (inherit `zyra_garment_merch.garment_order_view_form`):
- KPI strip `//div[@name='kpi_strip']` with named tiles `kpi_ex_factory`, `kpi_cut`, `kpi_sewn`, `kpi_packed`,
  `kpi_shipped`, `kpi_order_value`, `kpi_pp_sample`, `kpi_tna`, `kpi_margin` — materials adds "Fabric in house",
  quality "Final inspection", shipping "Cartons packed" (screen 2).
- Notebook `//notebook[@name='order_tabs']`, pages `size_colour`, `breakdown`, `sampling`, `tna`, `notes` —
  materials adds "Materials on the floor" / "Fabric reconciliation" after `breakdown`.
- `//div[@name='button_box']` — cutting adds Bundles. Header buttons: cutting adds "Propose Cut Plan", shipping
  adds "Pack Plan" (screen 2).
- The grid widget `zyra_size_colour_grid` (field widget for `line_ids`) shows cut / sewn / packed bars.

## Security
Everyone internal reads orders, grid, postings, samples, approvals and T&A. Merchandiser (so Factory Manager and
Admin): full on everything except postings (read + create). Postings: create for cutting, line supervisor,
quality, packing & shipping (the API uses sudo anyway); write/unlink only Garment Admin. Tech pack designer:
read/write samples and measurements; quality: write measurements. Floor roles may set actual dates on milestones.
Multi-company record rules on orders, grid, postings, samples, approvals, milestones; templates are shared or per
company.

## Demo
Sewing lines `workcenter_line_1..4`. Orders (`order_tee_late` from sale order `sale_order_tee`, 3 days past
ex-factory, 35 % shipped; `order_jean_late` 2 days late; `order_polo_running`; `order_chino_running`;
`order_tee_confirmed`; `order_oxford_draft` (style not approved); `order_polo_shipped` completed), postings,
T&A plans with on-time, late and overdue milestones; 12 samples in every stage (incl. a round-2 rejection and the
size-set sample `sample_polo_size_set` with 9+ measured points); 8 approval cards (resubmission asked, with buyer,
approved). Dates are relative to the install day. Loaded by `garment.merch.demo._load_demo()`.

## Tests (`tests/`, tag `zyra`) — 58
Grid built per colourway × size, form onchange, totals and value, removing a colourway, confirm rules (pieces,
approved style), amend-only changes, dates, size range, close short (FM only), mark completed, delete guard, sale
order → production order; progress API (adds, stages, corrections, every validation error, state advance, floor
role, immutable postings, closed order); late flags and search; sample verdicts (in / on the limit / out,
asymmetric tolerance, pending), counts, spec loading from the graded chart, workflow, remake round, overdue, PP
status on the order, invoicing; approval submissions, chosen option rule, options text, days to approval, overdue,
other open cards; T&A dates from template, on time / late / overdue, rescheduling, KPI; style figures; reports render.

## Decisions
- `garment.style` belongs to `zyra_techpack`; this module only `_inherit`s it and its form (KPI tiles + smart
  buttons). The **style kanban (screen 22) is not changed**: the screen shows no order figures on the cards.
- Order numbers use `PO/2026/0008` (screens) rather than the skill's `GO/` example.
- Order states keep the kit's list; `closed` is labelled "Completed" to match the status bar (Confirmed · In
  Production · Completed). "Mark Completed" requires everything shipped; "Close Order" closes short (FM only).
- Grid quantities are whole pieces (Integer). Progress is stored as postings (`garment.order.progress`), so every
  number on the order can be traced to a bundle/carton/shipment ref; that is the "Postings" smart button.
- Sewing line = `mrp.workcenter` (architecture says lines are work centres); sewing (wave 4) may add fields.
- Sample states/types follow screens 26–27 (added `salesman` and `shipment` types). A measured value of 0 counts
  as "not measured".
- Approval "Open" filter keeps cards approved in the last 60 days so the Approved column is not empty (screen 29).
- Costing is read softly with several candidate field names (`material_cost`/`making_cost`/`other_cost`/
  `margin_pct`/`fob_price`, `state == 'approved'`, `techpack_id` or `style_id`); see `docs/requests/zyra_garment_costing.md`.
  Without costing, "Costed FOB" is the average price of the style's orders.
- Screen-2 tiles owned by later waves (fabric in house, final inspection, cartons packed) and buttons
  (Propose Cut Plan, Pack Plan, Bundles) are left to those modules through the named extension points.
- KPI tile colours are fixed rules: ex-factory red when past, amber within 7 days; stage tiles green when the stage
  reached the ordered quantity, else amber.

## Not done yet
- "Materials on the floor", "Fabric reconciliation" and "Delivery splits" tabs (screen 2/34) — wave 3 / later.
- Planned cost section and margin tile appear only once `zyra_garment_costing` is installed and its field names
  match the soft read.
- PDF printing was checked as HTML render (tests); wkhtmltopdf output not reviewed.
