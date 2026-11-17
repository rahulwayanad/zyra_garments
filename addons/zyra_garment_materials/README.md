# zyra_garment_materials

Fabric and trim bookings per production order, fabric rolls (stock lots) on a roll board, and 4-point
fabric inspection with a tablet screen. Odoo 18 Community.

Depends: `zyra_garment_merch`, `zyra_garment_theme`, `purchase_stock` (and through merch: `zyra_techpack`,
`zyra_garment_base`).

## Models

### `garment.fabric.booking` (screens 39–40)
One booking per production order (`garment.order`) and material family (`booking_of`: `fabric` / `trims`).
- `order_id`, `buyer_id`, `style_id`, `techpack_id` (the order's tech pack revision), `booking_date`,
  `date_needed` (defaults to 3 weeks before the order's ex-factory date), `state`
  `draft → confirmed → ordered → in_house`.
- `line_ids` → `garment.fabric.booking.line`; `roll_ids` → `stock.lot`.
- Live figures: `materials_count`, `materials_in_house_count`, `materials_short_count`, `in_house_pct`,
  `value_to_order`, `qty_required`, `qty_in_house`, `roll_count`, `purchase_count`, `needed_in_days`,
  `is_short` (searchable), `shortage`.
- Buttons: Load materials (draft), Confirm, Raise POs (one RFQ per vendor for the "to order" quantity,
  PO lines linked back to the booking line), Purchase Orders / Rolls smart buttons, Print.

### `garment.fabric.booking.line`
Material per colourway (`colour_id` empty = "All" colourways).
- `qty_required` = Σ(pieces × consumption) × (1 + wastage %), from
  `zyra.techpack.material_requirements(qty_by_variant)` (contract `wave2_techpack.md`) and the order grid.
- `qty_in_stock` (received rolls not rejected; for untracked trims: received on booked POs),
  `qty_on_hand`, `qty_used`, `qty_open_po` (open PO lines not yet received),
  `qty_to_order` = max(0, required − in stock − open PO), `value_to_order`, `is_in_house`.

### `stock.lot` (inherited — rolls, screens 41–42)
Uses the base roll fields (`roll_status`, `dye_lot`, `shade_band`, `width_cm`, `gsm`, `points_per_100sqyd`,
`action_roll_approve/hold/reject`). Adds `booking_line_id`, `fabric_booking_id`, `garment_order_id`,
`roll_received_qty`, `roll_received_date`, `roll_supplier_id`, inspection links, and relaxation
(`relax_start`, `relax_until`, `relaxation_status`; hours from company `garment_relax_hours`, default 24).
Receiving a PO raised from a booking tags the received lots with the booking line / order
(`stock.move._action_done`).

### `garment.fabric.inspection` + `garment.fabric.inspection.defect` (screens 43–45)
4-point system. Defect length band ≤3" / 3–6" / 6–9" / >9" = 1 / 2 / 3 / 4 points, capped at 4 points per
linear yard. `points_per_100sqyd` = points × 3600 ÷ (inspected yards × cuttable width in inches).
`accept_limit` defaults from company `garment_fabric_accept_points` (base setting, 40).
`result` = pass / hold / reject (`result_override` lets the inspector hold or reject with a reason).
Finish (`action_done`): pass → roll approved; hold → roll on hold with the reason (auto reason
"4-point score X over the accept limit Y"); reject → roll rejected. Re-inspection that passes releases a hold.

Tablet screen: client action `zyra_garment_materials.action_fabric_inspection_tablet`
(tag `zyra_fabric_inspection_tablet`), big tap targets per defect × band, live points and verdict;
server API `tablet_queue`, `tablet_start(lot_id)`, `tablet_state`, `tablet_add_defect`, `tablet_undo`,
`tablet_set`, `tablet_finish`.

### `garment.order` (inherited)
`fabric_booking_ids`, `fabric_in_house_pct` (fabric received ÷ required, for the order KPI tile),
`fabric_booking_line_ids` (reconciliation tab), `action_view_fabric_bookings`.

## Menus
Under `zyra_garment_base.menu_garment_materials`: Fabric Bookings, Fabric Rolls (base menu repointed to
the roll board kanban), Fabric Inspections, Inspection Tablet.

## Reports
Fabric booking sheet, fabric inspection report, roll label.

## What other modules can rely on
- `garment.fabric.booking` / `.line` fields above; `garment.order.fabric_in_house_pct`.
- Roll `roll_status == 'approved'` means the roll passed inspection and may be cut (cutting reads it).
- `stock.lot.garment_order_id` / `fabric_booking_id` on received rolls.

## Decisions
- One booking per order **and** material family (fabric / trims) so the fabric store and the trims store
  work their own list; both come from the same tech pack call.
- BoM lines without colour become one "All" line instead of one per colourway.
- "In stock" for lot-tracked fabric = received length of rolls that are not rejected; for untracked trims =
  qty received on the booked PO lines.
- `is_short` = needed-in-house date passed and not every material in house.
- Needed-in-house date defaults to ex-factory − 21 days.
- Inspector may hold/reject a roll that passes on points (shade, smell, width) — reason is mandatory.
- Tablet = OWL client action calling model methods (no custom controller).

## Tests
`tests/test_four_point.py` (formula with known numbers, bands, per-yard cap, company limit, hold on fail with
reason, reject, re-inspection release, tablet API), `tests/test_booking.py` (required maths, shortfall
= required − stock − open PO, rejected rolls excluded, raise POs, receipt tagging, short flag, in-house %),
`tests/test_tablet.py` (client action loads, queue, tour).

## Not done yet
- The browser tour of the tablet screen (`test_tablet_inspection_tour_records_a_defect_and_finishes`) is
  skipped: the Odoo venv has no `websocket-client` package. The tablet API itself is tested server side.
- Screens 39–45 checked against the view code and demo data, not yet opened in a live browser.
