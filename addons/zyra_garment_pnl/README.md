# zyra_garment_pnl — Order P&L

What every production order really made: invoiced revenue against the planned cost of the approved cost sheet
and the actual material, making (wages), job work and other cost. Screens 74 (Order P&L list) and 75 (P&L of one
order); feeds the Order Profitability cockpit (screen 17).

- Depends: `zyra_garment_costing`, `zyra_garment_shipping`, `zyra_garment_jobwork`, `zyra_garment_wages`,
  `stock_account` (and through them merch, cutting, sewing, materials).
- Version `18.0.1.0.0`, licence OPL-1.

## Models

### `garment.order.pnl` — Order P&L (`mail.thread`), one per order (`unique(order_id)`)
A stored record, not an SQL view: figures are written by **Refresh** (button, `action_refresh()`), on create,
and by the nightly cron `ir_cron_refresh_order_pnl` (every order not draft/cancelled gets a P&L).

| Field | Meaning |
|---|---|
| `name` | "PO/2026/0035 · ST-0103" (order · style code) |
| `order_id`, `buyer_id`, `style_id`, `business_model`, `order_state`, `order_status` ("Closed"), `is_closed` (shipped or closed), `date_ex_factory` | from the order (stored) |
| `qty_ordered`, `qty_shipped`, `pieces_costed` | pieces costed = shipped pieces, the ordered pieces while nothing has shipped |
| `order_value`, `revenue` ("Invoiced") | order value = price × ordered; revenue = posted customer invoices − credit notes of the order |
| `planned_material`, `planned_making`, `planned_other`, `planned_cost` | merch's `planned_*_pc` (from the approved cost sheet) × pieces costed |
| `planned_margin_pct` | (revenue − planned cost) ÷ revenue × 100 |
| `actual_material`, `actual_making`, `actual_jobwork`, `actual_other`, `actual_cost` | see sources below |
| `cost_variance` | actual − planned (positive = over plan) |
| `margin`, `margin_pct`, `is_loss` | revenue − actual; ÷ revenue × 100; margin < 0 |
| `revenue_pc`, `cost_pc`, `margin_pc` | ÷ pieces costed |
| `cost_line_ids` | `garment.order.pnl.cost` (date, description, amount): other costs typed by finance |

Formula method: `_pnl_figures(src)` (pure, tested with the numbers of screen 75).

### Sources (each a method, read with `sudo()`)
| Figure | Source |
|---|---|
| Revenue `_src_revenue` | posted `out_invoice`/`out_refund` product lines with `account.move.line.garment_order_id` = order (field added here), plus lines of the order's shipment invoices (`garment.shipment.invoice_ids`) named "<order> · …" as shipping writes them |
| Material `_src_material` | done stock moves of fabric cut on the order's lays (`stock.move.garment_lay_id.order_id`) and of material issued to the order (`stock.move.garment_pnl_order_id`, field added here); value = − stock valuation layers, else qty × product cost |
| Making `_src_making` | wage lines paying the order's scans (`garment.scan.wage_line_id`): each line's net pay × (its minutes on this order ÷ its total minutes); cancelled sheets count nothing |
| Job work `_src_jobwork` | job-work POs of the order (`garment.jobwork.order.production_order_id`): posted vendor bill lines; a PO not billed yet counts at its untaxed amount |
| Other `_src_other` | P&L other-cost lines + samples of the order not charged to the buyer (`garment.sample.cost`) |

### Added to other models
- `garment.order.pnl_ids`, `garment.order._garment_pnl(refresh=True)` → P&L of each order (created if missing),
  `action_view_pnl` (stat button "P&L" on the order form, costing / factory manager / admin).
- `account.move.line.garment_order_id`, `stock.move.garment_pnl_order_id`.

## What other modules can rely on (cockpit)
- `env["garment.order.pnl"]._garment_profit_summary(domain=None)` → `{revenue, actual_cost, margin_pct,
  cost_vs_plan_pct, loss_count, loss_orders, margin_by_buyer: [{buyer, buyer_id, margin_pct}]}`; default domain
  = closed orders. Fields `is_closed`, `is_loss`, `date_ex_factory`, `buyer_id`, `business_model` for filters.
- `order._garment_pnl()` to get fresh figures for one order.

## Menus and views
- Garment › **Finance** (new section, seq 95; costing, factory manager, admin, merchandiser) › **Order P&L**
  (`action_garment_order_pnl`, default filter "Closed orders").
- List (screen 74): Order, Buyer, Revenue, Planned Cost, Actual Cost, Cost Variance, Margin %, Cost / PC; loss rows red.
- Form (screen 75): Refresh; KPI tiles Revenue, Actual Cost, Margin, Margin %, Planned Margin %, Cost Variance,
  Cost / pc; "Order profitability" title; groups Order, Pieces, Revenue, Planned Cost; chatter.
- Pivot (buyer × ex-factory month: revenue, actual cost, margin) and graph (margin by buyer); search group by
  Buyer, Style, Month.

## Security
Costing: read/write/create; Factory Manager and Admin: full; Merchandiser: read. Other-cost lines likewise.
Multi-company record rules on both models.

## Demo (`demo/pnl_demo.xml` → `models/pnl_demo.py`)
Three closed orders made from the demo styles (tee, polo, chino) with real source documents: a posted customer
invoice of the shipped pieces, material issued from stock, sewing sent out on job work (received and billed),
and other costs on the P&L. The polo order runs over plan and loses money (red row). The merch demo order that is
already closed gets the same documents (came in under plan). Every running demo order gets a P&L too.

## Tests (`tests/`, tag `zyra`) — 9, all green
One order end to end with known numbers (invoice, draft invoice ignored, material issue, job work bill, sample,
other cost → margin 140 / 46.67 %, planned margin 20 %, variance −80); planned cost from the approved cost sheet;
credit note reduces revenue; pieces costed = shipped else ordered; loss flag + cockpit summary; formula with the
screen 75 numbers; zero revenue; one P&L per order; floor sources (fabric cut on a lay = material, wage sheet
paying the order's scans = making).

## Decisions
- Stored record refreshed on demand / nightly instead of an SQL view: screen 75 has a Refresh button and chatter,
  and the sources (stock valuation, wage apportioning, bills) are not one SQL join.
- Planned cost is spread over the **pieces costed** (shipped), so a short shipment doesn't show as a saving;
  margin % and planned margin % are shares of the invoiced revenue (matches screen 75: 32.65 % = (1,724.80 −
  1,161.60) ÷ 1,724.80).
- Planned "other" = merch's `planned_other_pc` (processes + commercial/finance + commission + freight).
- Making = wages actually paid (net pay incl. top-up, overtime, incentive), shared by minutes; unpaid scans are
  not a cost until a wage sheet claims them.
- Job work not billed yet counts at the PO amount (the cost is committed once the PO is raised).
- Revenue from shipment invoices is matched by the line name shipping writes ("<order> · <style>"), because
  shipping does not tag invoice lines with the order; lines tagged `garment_order_id` always win.
- Order status shows "Closed" for merch's `closed` state (merch labels it "Completed"), as on screen 75.
- Form adds an "Actual Cost" / "Other Costs" notebook under the screen-75 groups: the actual cost build-up and the
  place to type other costs are not on the image but are needed to explain the variance.
- Demo sewing for the closed demo orders is done on job work, since the sewing/wages demo scans belong to the
  running orders.

## Not done yet
- Checked in headless Chrome (list, form, pivot) against screens 74-75; the chatter sits below the form at
  1440 px (Odoo puts it aside only on wider screens), unlike screen 75.
- Open demo orders show large making cost: the wages demo pays minimum top-ups over few pieces.
- Trims consumed through an MO (finished goods "Post to Stock") are not read; issue them with
  `garment_pnl_order_id` or type them as other cost.
- Multi-currency invoices are read in company currency (balance); no per-currency split.
