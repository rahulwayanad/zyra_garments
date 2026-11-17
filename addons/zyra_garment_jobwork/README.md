# zyra_garment_jobwork

Outsourced job work (sewing, washing, printing, embroidery) for the Zyra garment ERP (Odoo 18 CE): send
bundles or pieces to a subcontractor on a printed **delivery challan**, receive them back in one or more lots
(good / rejected), compare **process loss** with the allowed %, flag **overdue** orders and raise the
**purchase order** at the agreed rate for the accepted pieces only.

- Depends: `zyra_garment_cutting`, `zyra_garment_theme`, `purchase`, `stock`
- Version `18.0.1.0.0`, licence OPL-1. Screens: 59 (kanban by state), 60 (form).

## Models

### `garment.jobwork.order` — Job Work Order (`mail.thread`, sequence `JW/%(year)s/0001`)
| Field | Notes |
|---|---|
| `state` | `draft` → `sent` → `partly_received` → `received` → `billed`; `cancel` (draft only). Kanban columns sent / partly received / received / billed (`group_expand`) |
| `process` | `sewing`, `wash` (label Washing), `print` (Printing), `embroidery` |
| `production_order_id` | m2o `garment.order` (optional); `style_id`, `buyer_id` related, stored |
| `in_house`, `vendor_id` | vendor domain `is_jobwork_vendor`; required unless done in-house |
| `rate`, `allowance_pct` | agreed rate per piece; allowed process loss % (default 2) |
| `bundle_ids`, `qty_sent` | m2m `garment.bundle`; sent = sum of bundle pieces, or typed when no bundles |
| `receipt_ids` | o2m `garment.jobwork.receipt` (`date`, `qty_good`, `qty_rejected`) |
| `qty_good`, `qty_rejected`, `qty_short`, `qty_rejected_short`, `qty_pending` | stored; pending = sent − good − rejected − short |
| `process_loss_pct`, `loss_over_allowance` | loss = (rejected + short) ÷ sent × 100; flag when > allowance |
| `qty_billable`, `jobwork_value`, `bill_due` | billable = good pieces; value = billable × rate; bill due = value until billed |
| `is_overdue` | computed, searchable: state sent/partly received and expected date < today |
| `date_issue`, `date_expected`, `date_received`, `turnaround_days` | |
| `purchase_ids`, `purchase_count`, `move_ids` | POs and stock moves of this order |

Methods (other modules may call):
- `action_send()` — draft → sent; done stock move of `qty_sent` from the warehouse stock to location
  **Job Work Vendors** (`stock_location_jobwork`).
- `_garment_receive(qty_good, qty_rejected=0, date=None)` → `garment.jobwork.receipt`; refuses more than pending;
  moves the pieces back to stock; sets partly received / received (+ `date_received`).
- `action_close_short()` — pending pieces are written off as short (moved to the scrap location); state received.
- `action_bill()` — only when received; creates and confirms a `purchase.order` (product **Job Work Charge**,
  qty = good pieces, price = rate, no taxes) linked by `purchase.order.garment_jobwork_id`; state billed; chatter
  line "Purchase order … raised for a billable quantity of …".
- `action_print_challan()` — report `action_report_delivery_challan` (bundles, pieces, rate, signatures).

Also: `garment.jobwork.receipt.wizard` (Receive button), `stock.move.garment_jobwork_id`,
`purchase.order.garment_jobwork_id`; products `product_jobwork_pieces` (storable, moved to/from the vendor)
and `product_jobwork_service`.

## Menus
`menu_garment_jobwork` (Job Work, seq 60 under `zyra_garment_base.menu_garment_root`; toggled by the base
`area_jobwork` setting) › `menu_garment_jobwork_orders` (Job Work Orders, kanban/list/form, default filter Open).

## Security
Read for every internal user; create/write for Cutting and Line Supervisor; delete for Factory Manager.
Multi-company record rule. PO and stock moves are created with `sudo()` so floor roles can bill/send without
purchase or inventory rights.

## Tests (`tests/test_jobwork.py`) — 11, all green
Send moves pieces to the vendor location; send needs pieces and vendor; partial receipts and pending; receipt
cannot exceed pending; loss within allowance; loss over allowance counts short; billing quantity is accepted
pieces only (PO qty/price); billing refused before all back; overdue rule (draft and received never overdue,
searchable); not overdue before the expected date; challan renders.

## Decisions
- Stock is tracked with one generic storable product "Garment Pieces (Job Work)" rather than per style/size
  products: work-in-progress pieces have no product of their own in this ERP yet. The vendor location is an
  internal location so the pieces still count as ours while at the vendor.
- Billing creates a confirmed purchase order (vendor bill is made from it in Purchase as usual), at the agreed
  rate on good pieces only; rejected and short pieces are not paid.
- Short pieces are only known when the order is closed short; until then they are pending.
- Process loss = (rejected + short) ÷ sent; flag compares with the order's own allowance %.
- Production order is optional (job work can also be sent for samples).

## Not done yet
- Demo orders are not linked to a production order / bundles (screen 60 shows a linked PO/style/buyer).
- "Rejected or Short" and "Process loss" KPI tiles use fixed colours, not graded by value beyond the allowance flag.
- No vendor bill created automatically (PO only); no debit note for rejected pieces.
