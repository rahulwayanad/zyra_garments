# Build progress (overnight run, 16–17 Nov 2026)

Rahul authorised a full autonomous build overnight (back 08:00). Plan: `.agents/zyra_build_kit/build_prompts.md`.
Each wave: one subagent per module in its own git worktree (branch `feat/<area>`), own DB `zyra_<area>`;
then merge into `main`, install everything together on a fresh DB `zyra_gate`, run all tests.

**Resume rule:** read this file, run `git log --oneline -15` and `git worktree list`, then continue from the first
wave not marked merged. A module whose branch exists but isn't done: use the kit's "When a terminal stops
halfway" prompt.

## Decisions taken without Rahul (review at 08:00)
- `zyra_techpack` did not exist anywhere on this machine → built fresh to the T2 spec, no migration (no old data).
- Theme = `addons/zyra_garment_theme` (kit says so). The `.o_zg` token skill is reference only.
- Screens: `docs/screens/s001–s125.jpg` copied from `.agents/docs/design/screens/`; captions 1–100 from the design
  doc, 114–125 from the kit prompts, 101–113 unknown (decoration, backlog).
- Git repo initialised at `Garnaments/`; `odoo18/` and large reference files are git-ignored.

## Waves
| Wave | Modules | Status |
|---|---|---|
| 0 | repo, docs/screens, CLAUDE.md, theme installs | done (commit 7f9791c) |
| 1 | zyra_garment_base | **merged** bc2f3ed — gate: 31/31 tests, clean install |
| 2 | zyra_techpack, zyra_garment_costing, zyra_garment_merch | **merged** d58d49c — gate 156/156 tests, clean |
| 3 | materials, cutting, quality, shipping | **merged** (gate 375/375) |
| 4 | sewing, jobwork | **merged** (gate 339/339) |
| 5 | wages, pnl, cockpit, portal, connect | **merged** — final gate 431/431 (15 modules + suite), pushed |

## Log
- 16 Nov late: repo set up; odoo 18 + venv verified (theme installs clean, demo loads with `--without-demo=`).
- Hourly check-in job (:17) restarts the plan after any stall/usage-limit pause (session-only).
- Wave 1 started: zyra_garment_base agent.
- ~23:40 usage limit hit (resets 02:00); base agent stopped mid-way (models, data, libraries written, uncommitted).
- 02:40 base agent resumed from its transcript.
- ~02:55 base merged to main (gate 31/31). Wave 2 contract written (contracts/wave2_techpack.md): techpack owns garment.style. Wave 2 started.
- 03:14 techpack done (38/38 tests, contract met; BOM price_unit is Float not Monetary for sub-cent trims). Merged to main; wt-techpack kept until costing/merch finish (they test against it).
- costing done (29/29; added `rejected` state from screen 31; overheads/commission/margin as % of FOB). Merged. Incident: shared scratch dir let costing run merch's script once (dropped zyra_merch; merch recreates it each run) → preamble now gives each agent its own scratch dir.
- 03:31 merch done (58/58; progress API in its README). Merged. Wave 2 gate: base+techpack+costing+merch, 156/156, clean. Wave 3 started (quality exposes garment.order.final_passed; shipping soft-reads it).
- ~04:00 usage limit hit again (reset 07:30); all 4 wave-3 agents stopped mid-way. 07:31 Rahul said restart; all 4 resumed.
- Rahul: when everything is complete, push to git@github.com:rahulwayanad/zyra_garments.git (remote `origin` added).
- Remote origin/main has only 'Initial commit' (README.md, .gitignore). Plan at the end: merge origin/main with --allow-unrelated-histories (union .gitignore, keep their README content), then normal push of main (no force); leave 'release' untouched.

## Working-hours schedule (Rahul, 17 Nov 07:45)
Build runs only 18:00–09:00; Rahul needs his tokens 09:00–18:00.
- 08:55 one-shot: stop still-running wave-3 agents, commit WIP, log. No new work until evening.
- Daily 18:05 (fires ~18:35 with scheduler jitter): resume paused agents, continue waves, final gate, push to origin/main.
- Wave-3 agent ids for SendMessage resume: materials ad101fdcd2c44fcc6 · cutting a4396cb54d0ce18ee ·
  quality afe4500bdbe59b673 · shipping a66cac3ccd2c545c6
- Hourly :17 check-in removed (it would have restarted work in working hours).

## Usage budget (Rahul, 17 Nov ~07:55) — supersedes the working-hours schedule above
Rahul must keep >=20% of every 5-hour usage window for office work. Claude cannot read the usage meter, so a
fixed budget is used: measured ~4 agent-hours ≈ one full window → per segment max 3 agents for 60 min
(~2.5 agent-hours incl. orchestration), then 5 h rest. Never build 09:00–18:00.
- Today: pause at 08:10 (4 agents ran from 07:31).
- Segments start 18:05, 23:05, 04:05 (scheduler jitter: ~+30 min); each schedules its own pause 60 min later.
- Wave 5 (5 modules) runs as 3 + 2.
- Expected finish: ~4 segments → around 05:00 on 18 Nov, then push to GitHub.
- ~07:58 Rahul: usage at 53% (window from 07:30). Recalibrated: 4 agents × ~27 min ≈ 53%. Paused all 4 wave-3
  agents immediately; WIP commits: materials 14d49ae, cutting 07ddcd9 (2 tests failing, was fixing),
  quality 39865c0, shipping 8dc92b0. New segment rule: max 3 agents × 35 min, starts 18:05/23:05/04:05
  (next fire 18:07), pause scheduled by each segment. 08:10 pause job cancelled (already paused).
- ~08:05 Rahul controls restarts from his phone (Remote Control). All automatic segment jobs cancelled; build only runs on his command. Sleep blocked for 3 days so the PC stays reachable.
- 08:05 Rahul: "start my garments" (usage 56% session, resets 12:29). Short segment: fresh agents resumed cutting
  (port 8092) and materials (port 8091) from their WIP commits, hard stop 08:33. Quality and shipping stay paused.
- 08:08 segment (requested from Rahul's phone session): cutting + materials resumed, hard stop 08:33 (one-shot job). Quality, shipping stay paused (usage 56%).
- 08:10 STOP (from Rahul's phone session): usage 71% and rising. cutting + materials stopped, no odoo test runs left, WIP committed, 08:33 job cancelled. NO BUILD UNTIL RAHUL SAYS (Rahul 08:12).
- 08:12 scheduled one-shot 18:00 segment (fires ~17:59): cutting+materials+quality (max 3), shipping when one finishes; 40-min cap with self-scheduled hard stop; then wait for Rahul.
- 08:13 18:00 restart cancelled (Rahul: "I will tell when need to start"). NO BUILD UNTIL RAHUL SAYS (Rahul 08:12). No scheduled jobs.
- 14:04 START (Rahul via phone session: "start now"; session usage 2%, resets 17:50; week 62%; office-hours run allowed).
  Fresh agents resumed cutting (port 18102) and materials (port 18101) from their WIP commits. Quality agent launch
  was blocked by the permission classifier, so quality and shipping stay paused. Hard stop job at 14:47 (segment ends 14:50).
- 14:10 cutting done (47/47, coupon payload contract in its README) → merged dbb8252; gate base..cutting 203/203, clean.
  Shipping agent started in cutting's slot (port 18104).
- 14:15 materials done (41 tests; browser tour skipped: websocket-client missing from the venv) → merged 821078d;
  gate base..materials 238/238, clean. Quality still paused (launch blocked; waiting for Rahul's OK to retry).
- 14:19 shipping done (43/43, demo on merch orders, final_passed soft-read) → merged 0fa3acf; gate base..shipping
  (7 modules) 281/281, clean. Worktrees wt-cutting, wt-materials, wt-shipping removed (branches kept).
  Wave 3 left: quality (paused at 39865c0; its launch was blocked, retry needs Rahul's OK).
- 14:46 WAVE 4 START (Rahul via phone session, 14:37 "start next task"; session usage 23%). Worktrees wt-sewing
  (feat/sewing, DB zyra_sewing, port 18105) and wt-jobwork (feat/jobwork, DB zyra_jobwork, port 18106) from main 04756c0.
  14:47 stop job replaced by hard stop at 15:12 (segment ends 15:15). Quality still paused.
- 14:55 jobwork done (11/11; demo orders not linked to a production order: merch demo has no xml ids) → merged
  f3d75d0; gate 8 modules 292/292, clean. wt-jobwork removed (branch kept). Sewing still running.
- 15:05 sewing WIP 31488d6 (feat/sewing, NOT merged): core done, 8/8 tests, clean install — garment.line wraps
  mrp.workcenter, bulletin + line balancing wizard, scans with offline sync batch, 'sewn' progress, daily summary and
  hourly board methods, demo. Not done: client actions for screens 3 (planning board), 4 (scan station with offline
  queue), 56 (line TV board), 58 (daily summary); screens 54/55 not laid out like the images yet.
- 15:05 STOP: segment closed early (no agents running, no odoo runs left, 15:12 job cancelled). Main 8 modules gated
  292/292. Left: quality (paused 39865c0, launch blocked), sewing floor screens, then wave 5.
  NO BUILD UNTIL RAHUL SAYS. No scheduled jobs.
- 15:02 SEGMENT START (Rahul via phone session, 15:01 "start next task"; session usage 35%, week 67%). Sewing resumed
  (floor screens 3/4/56/58, layouts 54/55); portal (wt-portal, feat/portal, DB zyra_portal, port 18107) and connect
  (wt-connect, feat/connect, DB zyra_connect, port 18108) started from main 41a76f0. Hard stop job 15:42 (ends 15:45).
  Wages may start only if sewing merges before the stop. Quality still paused.
- 15:12 Rahul's usage 54% (from 35% at 15:01) → hard stop moved to 15:20.
- 15:11 portal done (6/6 HttpCase) → merged 378a15b; gate 9 modules 298/298, clean. wt-portal removed.
  Review for Rahul: vendor nav is Home / Job work (screen shows Orders / Styles), extra Approvals page not on any screen.
- 15:14 sewing WIP 60a3710 (NOT merged, 14/14): screens 4 (offline scan station), 56 (TV board), 58 (daily summary,
  garment.line.day), 3 (planning board, garment.line.plan), 54 (bulletin versions) built. Left: 55 as a saved LB/
  record (fractional operators, draft/applied), 58 Defects tab + Print Hourly Report, browser check of 3/4/56.
- 15:16 connect done on branch b9ca13c (28/28, clean), NOT merged: no time for the gate before the stop → gate+merge
  first next segment. Left: bundle.cut/final.failed/shipment.left webhooks must be emitted by cutting/quality/shipping
  (_garment_emit; request file still to write), cockpit line chart, screen 118 columns, AI reading 116–117 (optional).
- 15:17 STOP: no agents, no odoo runs, no scheduled jobs. Wages not started. NO BUILD UNTIL RAHUL SAYS.
  Next: gate+merge connect; finish sewing (55, 58 extras) → merge; quality (needs Rahul's OK); wages, pnl, cockpit.
- 15:55 SHORT SEGMENT (Rahul via phone 15:54; usage 61%). Hard stop 16:11. connect merged ce466ea after gate
  10 modules 324/324, clean; wt-connect removed. Sewing agent resumed for screen 55 (saved LB/ record) + 58 extras.
- 15:57 sewing done (15/15: screen 55 as saved LB/ record, 58 Defects tab + hourly report) → merged 621d8f1; gate
  11 modules 339/339, clean. wt-sewing removed.
- 16:00 STOP (segment done early; 16:11 job cancelled). No agents, no odoo runs, nothing scheduled. Not pushed.
  Merged: base, techpack, costing, merch, materials, cutting, shipping, jobwork, sewing, portal, connect (11/15).
  Left: quality (paused 39865c0, needs Rahul's OK), wages, pnl, cockpit. Open for Rahul: portal vendor menu +
  Approvals page; connect webhooks bundle.cut/final.failed/shipment.left need emit calls in cutting/quality/shipping.
  NO BUILD UNTIL RAHUL SAYS.
- 16:19 WAGES SEGMENT (Rahul via phone; usage 68%). 16:23 wages core on feat/wages 302a4d5 (NOT merged, 4/4 tests,
  clean install): rate card, weekly wage sheet from scans (top-up, overtime, incentive), scan→wage line no double
  count, balanced journal entry, wage slip PDF. Left: screens 77–81 per images (KPI tiles), demo data.
  16:24 STOP: no agents, no odoo runs, nothing scheduled. Not pushed. NO BUILD UNTIL RAHUL SAYS.
- 16:24–16:29 tiny wages segment (usage 72%): wages WIP fcd32d4 on feat/wages (NOT merged, 4/4, clean): demo rate card +
  floor sheet from sewing demo scans (all operators on minimum top-up: demo pieces too low), KPI tiles on sheet form.
  Left: match screens 77–81 to images (not opened yet), richer demo so piece earnings exceed the minimum.
  STOP: no agents, no odoo runs, nothing scheduled. Not pushed. NO BUILD UNTIL RAHUL SAYS.
- 16:27 FULL RUN (Rahul via phone: "Now, anyway"; 80% cap lifted for this run only). Hard stop job 18:42 (ends 18:45).
  Wages resumed (screens 77–81, richer demo). Quality launched (this time it was allowed). P&L after wages merges
  (depends on wages), cockpit after P&L. Portal fixes untouched. No push.
- 16:33 quality done (36 tests, tour skips without websocket-client) → merged; first gate 5 errors in shipping tests
  (quality's final_passed blocked test orders). Integration fix in shipping tests (patch final check except the
  rule's own tests) → gate 12 modules 375/375, clean. wt-quality removed. Wave 3 complete.
- 16:49 wages done (11/11, screens 77–81 matched, approve step, cancel posted sheet) → merged f076c00; gate 13 modules
  386/386, clean. wt-wages removed. P&L started.
- ~17:00 usage limit hit (100%) during P&L; resumed 18:05 on Rahul's "next" (window reset 17:50).
- 18:08 pnl done (9/9, screens 74/75, _garment_profit_summary for cockpit) → merged 61fb097; gate 14 modules 395/395,
  clean. wt-pnl removed. Stopped a leftover headless Chrome from the overnight techpack agent. Cockpit started.
- 18:3x cockpit WIP 637addb on feat/cockpit (NOT merged, 14/14, clean install): garment.cockpit data layer for
  cockpits 1, 5–17 (+21 present mode), one OWL client action, screen 1 complete, screen 5 filter bar. Left: own layouts
  for cockpits 6–17 (now one generic layout), shift split, buyer filter beyond Factory Pulse, browser check.
- STOP (full run ended; 18:42 job cancelled). No agents, no odoo runs, nothing scheduled. Not pushed.
  Merged 14/15: base, techpack, costing, merch, materials, cutting, quality, shipping, sewing, jobwork, wages, pnl,
  portal, connect — gate 395/395. Open for Rahul: portal vendor menu + Approvals page; connect webhook emits in
  cutting/quality/shipping; browser check of all screens. NO BUILD UNTIL RAHUL SAYS.
- 17 Nov 13:4x (Rahul, direct request): new umbrella app `zyra_garment_suite` ("Garment Suite") depends on all 14
  merged modules + theme; base no longer `application`; root menu and Settings app renamed "Garment" → "Garment
  Suite". Spec `.agents/docs/modules/zyra_garment_suite.md`. Fresh DB install of the suite alone: 3/3 suite tests,
  gate 398/398 (361 tagged `zyra` + connect 28 + jobwork 13 — those two modules' tests lack the `zyra` tag), clean.
  Add `zyra_garment_cockpit` to the suite's depends when it merges.
- 17 Nov 19:xx (Rahul, direct request "Create garments demo data, give me a deep workflow of one full sale"): demo
  story in `zyra_garment_suite` (`models/suite_story_demo.py`, `demo/suite_story_demo.xml`, 5 tests): Coastline
  Outfitters, ST-0201, 1,100 pcs, enquiry → paid → wages → P&L → completed, all through the modules' own APIs.
  Walkthrough `.agents/docs/full-sale-walkthrough.md`. Gaps filed: docs/requests/zyra_garment_shipping.md (Post to
  Stock re-consumes fabric from other orders' rolls incl. a held roll — high; SO stays to deliver/invoice; invoice
  lines untagged), zyra_garment_pnl.md (MO trims not read), zyra_garment_merch.md (freight in planned other on FOB).
- 17 Nov 14:1x (Rahul: "Start cockpit") cockpit finished in-session (no subagent): every cockpit (1, 5–17) now has
  its own layout from the screens — subtitle, coloured headline, tiles, and its panels (stacked/grouped bars with
  value labels, lines with a dashed limit, doughnuts, ranked bars, tables with progress bars/badges). Buyer and
  business-model filters apply to all cockpits. Fixed: failed finals counted `result = 'fail'` (never matched;
  value is `failed`); chart redraw on tab switch; pieces-to-pack no longer goes negative on over-packed orders.
  Browser check: all 14 tabs open in headless Chrome, no JS errors, screenshots compared with s001, s005–s017.
  Found: Chrome stores India as `Asia/Calcutta`, which this PostgreSQL (Ubuntu 26.04, no `tzdata-legacy`) rejects
  → every by-day group crashes (also standard Odoo). Needs `tzdata-legacy` on the server — noted in cockpit README.
  Cockpit 30/30; added to `zyra_garment_suite`. Gate on fresh DB `zyra_gate` via the suite: 15 modules + suite,
  426/426, clean. Merged. Not pushed. Left: shift split (Day/Night) not built.
- 17 Nov 14:2x (Rahul: "only garments related demo data"): `tools/load_garment_demo.py` loads the demo of every
  installed zyra_* module (dependency order, Odoo's own loader) into a DB created without demo — no Odoo sample
  data. Proved on fresh `zyra_demo`: base demo off, 15 zyra modules with demo, 11 orders / 6 styles / 4 invented
  buyers, 0 Odoo sample partners or demo users; a second run is refused. Usage in `tools/README.md`.
- 17 Nov evening: feat/cockpit merged into main (aabf23c, log conflict kept both entries). Final gate on fresh
  zyra_gate via zyra_garment_suite: 15 modules + suite, 431/431, clean. Pushed main to origin (Rahul's request).
- 17 Nov 19:5x (Rahul, direct request "insert garments demo data to db"): demo loaded into the `garments` DB with
  Odoo's `force_demo` (all installed modules incl. standard Odoo apps; 0 demo failures, 0 warnings). Full-sale story
  = PO/2026/0011. Backup before: ~/odoo-backups/garments_before_demo_20261117_1951.dump (+ filestore .tgz).
