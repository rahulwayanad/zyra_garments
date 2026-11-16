# Project plan — Garment Factory ERP on Odoo 18 CE

Source of truth: the Claude Doc "Building a Garment Factory ERP on Odoo 18 CE in 4 Days with Claude Code"
(https://claude.ai/artifact/7pnb5a9X9GGpVCuQC2iLty, owner: Rahul). This file mirrors it for agents. If the two
disagree, ask Rahul which one is current, then update the other.

## The problem

A cut-and-sew garment factory runs on paper long after its accounts move to software. Tech packs live in PDFs,
cutting is tracked on lay slips, sewing output is counted by hand every hour, and piece-rate wages are added up in
spreadsheets at the end of the week. By the time a manager learns an order is late, the ex-factory date has passed.

## The goal

Put the whole flow, from tech pack to export carton, into **Odoo 18 Community**: **fifteen modules of our own**,
written and tested by Claude Code in **four working days** (17–20 Nov 2026), then rolled out to the factory over
the following **eight weeks**.

## Why build our own

There is a full garment ERP on the Odoo app store — *Garment Factory ERP* (`mn_garment`). We use it as our
**feature reference only** (see `reference/feature-reference.md`). We do not use its code:

- **Version.** It is built for Odoo 19. Our clients and our existing `zyra_techpack` module run on Odoo 18.
- **Licence.** It is OPL-1, which forbids copying or redistributing its code. Everything here is a
  **clean-room build**: features from its screenshots and our own analysis — never its code, images or text.
- **Community edition.** Odoo 18 CE has no Quality, PLM, Barcode or Planning apps. A garment factory needs all
  four, so they are part of what we build.

Building our own also means the modules can be sold to other factories later, and the existing techpack work
becomes the core instead of being thrown away.

## What we are building

Fifteen modules, one per department, in the order work moves through the factory. Full list, dependencies and
Odoo touch-points: `architecture.md`.

The tech pack and its cost sheet come first (`zyra_techpack`, refactored, not rebuilt). Merchandising turns an
approved style into a production order with its size-and-colour grid; materials books and inspects fabric;
cutting lays it up and bundles it; the sewing floor scans every bundle through every operation; quality inspects
the lots; packing ships them. Job work, wages and order P&L hang off the steps that feed them; cockpits, portals
and the API read across all of it. Everything stands on `zyra_garment_base` and standard Odoo apps: a fabric roll
is an Odoo stock lot, a finished order posts a manufacturing order, and wages post a journal entry.

## How each module is built (the loop)

Nothing is merged until Odoo itself has accepted it. Details: skill `odoo18-module-dev`.

1. **Spec.** Rahul gives the module's scope, the matching reference screens and the business rules.
2. **Write.** Models, security, views, reports, demo data and tests — each module in its own git worktree.
3. **Prove.** Install on a real Odoo 18 + PostgreSQL database, run the tests, open every screen in a browser,
   fix whatever fails.
4. **Merge.** Only when it installs cleanly alongside everything already merged and all tests pass.
5. **Review.** Each evening Rahul and a garment functional consultant walk the day's screens and list fixes for
   the next morning.

**Daily gate:** every module built so far installs together on a fresh database, every test green. Nothing
broken is carried into the next morning.

## The four build days

| Day | Date | Scope |
|---|---|---|
| 1 | Tue 17 Nov 2026 | **Foundation & merchandising.** Base module: setup wizard, 11 roles, shared libraries (sizes, colourways, points of measure, defects). Tech pack reshaped around a *style* with versioned tech packs and a BOM per colourway and size. Costing: versioned cost sheet with a margin floor. Merchandising: samples, buyer approval cards, production order with size-and-colour grid, time-and-action calendar. **Exit:** a style travels from enquiry to a confirmed order. |
| 2 | Wed 18 Nov 2026 | **Materials, cutting, job work, quality.** Fabric bookings; rolls as stock lots with shade and shrinkage; 4-point inspection on a tablet. Cut plans, lays, bundles, bundle tickets with a QR coupon per sewing operation. Outsourced job work with delivery challan. AQL inspections — a failed final blocks the shipment. |
| 3 | Thu 19 Nov 2026 | **Sewing floor & wages.** Operation bulletin, line balancing, planning board, a scan station that keeps working when Wi-Fi drops, TV board above each line. Piece-rate wage sheets built from the scans, posting a journal entry. Hardest day: operators, not office staff, use these screens. |
| 4 | Fri 20 Nov 2026 | **Shipping, finance, platform.** Pack plans, SSCC cartons, shipments, letters of credit; order P&L; buyer and vendor portals; API with webhooks; CSV imports with a dry run; a cockpit per department. **Exit:** all 15 modules installed together and one demo order running tech pack → shipped cartons. |

## After the code (rollout)

| Phase | Dates |
|---|---|
| Build with Claude Code | 17–20 Nov 2026 |
| Review & fixes (key users try every screen) | 23–27 Nov 2026 |
| Real master data (dry run on every import) + scanners, tablets, label printers on the floor | 30 Nov – 11 Dec 2026 |
| **Pilot go-live:** one buyer, one sewing line, paper in parallel for a week | 14 Dec 2026 |
| User acceptance tests, signed off per role | 4–8 Jan 2027 |
| **Full go-live** | 11 Jan 2027 |
| Hypercare: daily fixes and training | 11–29 Jan 2027 |

## Risks and guards

A four-day build moves the risk from writing code to checking it.

- **Rules nobody checked** → tests whose names state the rule in plain words; consultant review every evening;
  a full review week before real data.
- **Wrong Odoo 18 calls** → nothing merges until it installs and passes on real Odoo 18 and every screen has
  been opened in a browser.
- **Floor screens that need more than a day** → scan station, planning board and TV board get working first
  versions in the build; polished with supervisors in review week.
- **Operators who don't scan** → one line first, large-type scan screen, paper counts in parallel for a week.
- **Wages that don't match** → one week of parallel calculation must agree with the current method before
  wages go live.
- **Scope creep** → decoration, compliance and made-to-measure stay in the backlog until after go-live.

## Closing

The first plan needed a team of five and 33 weeks. With Claude Code the code shrinks to four days; what remains is
sitting with the merchandisers, store keepers, cutters and line supervisors until the system matches how their
factory runs. That still takes eight weeks, and it should.
