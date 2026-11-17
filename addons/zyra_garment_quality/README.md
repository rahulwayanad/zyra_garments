# zyra_garment_quality

Quality for the Zyra garment ERP: inline, end-line and final inspections, DHU, AQL sampling plans for the final
inspection, a tablet end-line check, CAPAs raised from repeated defects and the printed final inspection report.
A failed final inspection blocks the shipment of its order.

Depends on `zyra_garment_base` (defect library `garment.defect`, roles, menus), `zyra_garment_theme`,
`zyra_garment_merch` (`garment.order`).

## Contract other modules rely on

On `garment.order` (stored, searchable, do not rename):

| Field | Type | Meaning |
|---|---|---|
| `final_passed` | Boolean | True when the **latest completed final inspection** passed or was accepted under concession. False when there is none or the latest one failed. **Shipping must refuse to ship when False.** |
| `final_inspection_state` | Selection `none` / `passed` / `failed` | Same thing with "not inspected" told apart from "failed". |
| `final_inspection_id` | Many2one `garment.inspection` | The latest completed final inspection. |
| `inspection_ids`, `inspection_count` | | All inspections of the order. |

`zyra_garment_shipping` soft-reads it: `if 'final_passed' in order._fields and not order.final_passed: …`.
Latest = highest (date, id) among completed finals, so a passing re-inspection releases the order.

The production order form gets a "Final inspection" KPI tile (screen 2) in `kpi_strip` and a search filter
"Final Inspection Failed".

## Models

- `garment.inspection` — `kind` inline / endline / final; `order_id`, `style_id`, `buyer_id`, `line_id`
  (`mrp.workcenter`, defaults from the order), `inspector_id`, `date`, `pieces_checked`, `defect_line_ids`;
  counts `critical_count` / `major_count` / `minor_count` / `defect_count`; **DHU = defects × 100 ÷ pieces checked**
  (0 when nothing checked). Final only: `lot_size`, `aql_major` (2.5), `aql_minor` (4.0) → `code_letter`,
  `sample_size`, `major_accept/reject`, `minor_accept/reject`. `state` in_progress / completed; `result` pending /
  passed / failed / concession; `fail_reason`. Re-inspection link `reinspection_of_id`. Sequence `QI/YYYY/NNNNN`.
- `garment.inspection.defect` — defect line: `defect_id`, `severity` (defaults from the library, editable),
  `position` (collar, front left/right, sleeves, back, hem, side seams…), `qty`, `date`. Creating lines runs the
  CAPA trigger.
- `garment.inspection.hour` — pieces and defects per hour of an end-line session (hourly DHU on the tablet).
- `garment.capa` — title, `source`, `defect_id`, `position`, `line_ids`, `style_id`, `order_id`,
  `inspection_ids`, `first_seen`, `occurrences` over `occurrence_days`, `root_cause`, `action`, `owner_id`,
  `due_date`, `verification`; states open → in_progress → verified → closed (closing needs root cause, action and
  owner). Sequence `CAPA/YYYY/NNNN`.
- `garment.aql.lot.range` (ISO 2859-1 Table 1, levels I–III) and `garment.aql.limit` (Table II-A for one AQL, arrows
  already resolved) — editable data, loaded for general level II with AQL 2.5 and 4.0 (plus the other levels' letters).
- `res.company` — `garment_aql_major`, `garment_aql_minor`, `garment_dhu_limit` (5 %), `garment_capa_threshold`
  (10), `garment_capa_window_days` (3); in Settings.
- Wizard `garment.inspection.concession.wizard` — factory manager accepts a failed lot with a reason.

## Rules
- Final: fails on any critical, majors above the major accept number, or minors above the minor accept number
  (`fail_reason` says which). Cannot complete before the sample is checked. The sample is the larger of the major
  and minor plans, never more than the lot.
- Inline / end-line fail only on a critical defect.
- CAPA trigger: the same defect at the same place on the same line reaching the company threshold within the window
  raises one CAPA (posted by OdooBot); an open CAPA for that key is updated, not duplicated.
- Only the Factory Manager may accept a failed final under concession.

## Menus (Quality root from base)
Inspections (61) · Final Inspections (62, form 63) · End-line Check (client action `zyra_garment_endline_check`,
tablet, 64) · Corrective Actions (65). Configuration › Quality › AQL Code Letters / AQL Accept / Reject.
Reports: Final Inspection Report (66, `zyra_garment_quality.action_report_final_inspection`), CAPA Report.

## Security
Everyone reads; Quality inspector full rights; Line supervisor creates/edits inspections (no delete) and edits
CAPAs. Multi-company record rules on inspections, defect lines, hours and CAPAs.

## Demo
Inline, end-line and final inspections on the merch demo orders (a failed final on PO/2026/0001 and 0002, passed on
0003 and 0007), today's tablet session, two CAPAs (one auto-raised).

## Decisions
- `final_passed` counts a concession as passed (the manager has taken responsibility).
- AQL tables are records, not code, so a buyer's own AQL can be added without a release.
- The end-line tablet is an OWL client action that writes one daily session per line and an hourly row; the
  "Online" pill reflects the browser's connection only (no offline queue in this module).
- The browser tour test is skipped (quietly, via `unittest.skipUnless`) when `websocket-client` is not installed
  in the venv; Odoo would otherwise log a WARNING. Install `websocket-client` + Chrome to run it.

## Not done yet
- Tablet offline queue (sewing's scan station owns that pattern).
