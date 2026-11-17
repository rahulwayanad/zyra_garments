# zyra_garment_portal — Buyer and job-work vendor portal

Portal pages for the Zyra garment ERP (Odoo 18 CE). A **buyer** follows their production orders, styles and
time-and-action plan and approves samples and lab dips; a **job-work vendor** sees the jobs it holds.
Screens 122–125.

- Depends: `portal`, `zyra_garment_merch`, `zyra_garment_shipping`, `zyra_garment_jobwork`
- Version `18.0.1.0.0`, licence OPL-1. No new models; one helper on `res.partner`.

## Pages (controller `controllers/portal.py`, templates `views/portal_templates.xml`)
| URL | Screen | What |
|---|---|---|
| `/my/garment` | 122 | KPI tiles Open orders · Late (red when > 0) · Styles · Next ex-factory; "Your production orders" (order, style, ex-factory, packed bar + %, status) and "Styles" (style, season code, tech pack `v<revision>`). A vendor is redirected to `/my/garment/jobwork`. |
| `/my/garment/orders` | 123 | Order, Your PO, Style, Ordered, Packed, Shipped, Ex-factory, Status pill (On track / Late / Shipped) |
| `/my/garment/orders/<id>` | 124 | KPI tiles Ordered · Sewn (green) · Packed (amber) · Ex-factory (red when late); progress by colourway per stage (Ordered, Cut, Sewn, Packed, Shipped + Total) from `garment.order._garment_get_grid()`; T&A milestones (planned / actual) |
| `/my/garment/styles` | – | style list (season, tech pack version, open orders) |
| `/my/garment/approvals` | – | samples and approval cards **with the buyer**, with Approve / Reject (sample) and Approve / Resubmit (card, with option chooser) and a comment |
| `POST /my/garment/sample/<id>/decide` | – | `decision=approve\|reject`, `comment` → `garment.sample.action_approve/action_reject`; comment saved in `buyer_comments` and the chatter |
| `POST /my/garment/approval/<id>/decide` | – | `decision=approve\|reject`, `option_id`, `comment` → `chosen_option_id`, `garment.approval.action_approve/action_ask_resubmission` |
| `/my/garment/jobwork` | 125 | Job, Work (process · note), Order, Sent, Expected back, Pending pieces, Status (Overdue / Due) for jobs in state sent / partly received |

A "Garment portal" link is added at the top of the standard `/my` page. Styling: `static/src/scss/portal.scss`
(frontend bundle), light theme only.

## Security
- `ir.model.access`: `base.group_portal` **read only** on `garment.order`, `garment.order.line`,
  `garment.tna.milestone`, `garment.sample`, `garment.approval`, `garment.approval.option`, `garment.style`,
  `garment.jobwork.order`.
- Record rules (portal group only): orders, grid, milestones → `buyer_id child_of user.commercial_partner_id`
  and order not draft; samples, approval cards (+ options), styles → `buyer_id child_of` the user's company;
  job-work orders → `vendor_id child_of` the user's company and not draft.
- Controllers **search with the portal user's own environment**, so the rules decide what is listed. A detail page
  or a decision POST first checks read access as the user and answers **404** for anything that isn't theirs.
  Only display values and the approve/reject actions run with `sudo()`, after that check.
- Internal users can open the pages too (they see what they can read in the backend).

## What other modules can rely on
- `res.partner._garment_portal_kind()` → `'buyer'`, `'vendor'` or `False` (from `is_garment_buyer` /
  `is_jobwork_vendor` of the commercial partner).
- The routes above and the template ids `portal_garment_layout`, `portal_garment_home`, `portal_garment_orders`,
  `portal_garment_order`, `portal_garment_styles`, `portal_garment_approvals`, `portal_garment_jobwork`
  (inherit them to add columns, e.g. shipping documents).

## Demo
Portal users (password = login, demo only): `buyer.portal` (Nina Abbott, Northwind Apparel Ltd) and
`vendor.portal` (Nikhil Anand, Kerala Embroideries). One extra job `demo_jw_kerala_print` (printing · front,
linked to `order_tee_confirmed`) so the vendor page shows one overdue and one due job. Checked by fetching every
page as both demo users: home 2 open / 1 late, orders list, order detail with 3 colourways and 11 T&A
milestones, 1 sample + 2 lab dips waiting, vendor page with 2 jobs.

## Tests (`tests/test_portal.py`, HttpCase, tag `zyra`): 6, all green
- A buyer cannot read another buyer's order (record rule; styles too).
- Another buyer's order page answers 404.
- Buyer pages render with the buyer's own data (home, orders, order detail with colourway grid, styles, approvals).
- The vendor sees its own jobs with pending pieces and Overdue; buyers see no jobs; the vendor cannot read orders.
- A buyer approves a sample, and a lab dip with the chosen option, from the portal.
- Another buyer's decision POST gets 404 and changes nothing.

## Decisions
- Own top bar (company initials + name, Home/Orders/Styles, "<company> · buyer portal", user initials) instead of
  the standard portal header, to match screens 122–125. Added an **Approvals** nav link (the prompt asks for
  portal approvals; no screen shows it). The vendor nav shows Home / Job work instead of Orders / Styles: a vendor
  has no orders or styles to see (screen 125 shows the buyer nav, taken as a mock-up shortcut).
- Draft orders are hidden from buyers (not agreed yet). Cancelled orders are not listed.
- Home "Your production orders" lists open orders (confirmed / in production / packed); its pill shows the order
  state label (screen 122). The orders-list status is derived: Shipped (shipped or completed), Late (`is_late`),
  else On track (screen 123).
- Vendor "Work" column = process label · job note (jobwork has no separate work-detail field).
- Status "Due" = sent and not overdue.
- Shipping is a dependency as the prompt says, but no shipping data is shown yet (no screen asks for it).

## Not done yet
- Pages checked as rendered HTML (tests + fetching the demo pages); not compared side by side in a browser.
- No portal pagination/search (lists are short per buyer); no PDF downloads (breakdown, packing list) on the portal.
