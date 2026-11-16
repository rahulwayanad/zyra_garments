# Zyra light theme

> The binding designs are the 125 screens in `screens/` (doc "Zyra Garment ERP: Screen Designs"). Where they
> differ from the tokens or mockups below, the screens win: once the images are downloaded, re-check these
> tokens against them and update this file.

The default UI theme for every Zyra garment module. Mockups (Design canvas):
https://claude.ai/artifact/V5fPbqrDv1kJZf6gwNuCVt — sources copied to `mockups/*.dc.html`:

| Board | File |
|---|---|
| Tokens & components | `mockups/Main.dc.html` |
| Sewing Floor cockpit | `mockups/Cockpit.dc.html` |
| Production order form | `mockups/ProductionOrder.dc.html` |
| Line planning board | `mockups/PlanningBoard.dc.html` |
| Scan station (tablet) | `mockups/ScanStation.dc.html` |

Implementation guide and SCSS tokens: skill `zyra-light-theme` (`.agents/skills/zyra-light-theme/`).

## Principles

1. White surfaces on a soft lavender ground; **one** violet accent.
2. Status colours come in three steps: **ink** (text on white, ≥4.5:1), **soft** (tile fill), **chart** (bars, dots).
   Never put a chart colour on white as text.
3. Borders do the work glows/shadows did in the dark theme. One soft shadow on floating panels only.
4. Every number in a monospace face so columns line up. Labels: mono, 11px, uppercase, +10% tracking.
5. Cockpits open with one sentence naming the worst thing, then a KPI rail, then charts.
6. Floor screens (scan station, tablet inspection, TV board): 44px minimum touch targets, 28px+ input text.

## Tokens

| Token | Hex | Use |
|---|---|---|
| `ground` | `#F6F5FB` | page background |
| `surface` | `#FFFFFF` | cards, panels, forms |
| `surface-sunk` | `#F1EFF8` | inner wells, table header rows |
| `border` | `#E3E0EE` | all 1px borders |
| `border-strong` | `#D6D2E4` | secondary buttons, inputs |
| `text` | `#1B1830` | body text (16.9:1) |
| `text-muted` | `#5B5670` | labels, captions (6.6:1) |
| `text-quiet` | `#4D4868` | nav links, secondary values |
| `accent` | `#5B3FD0` | primary buttons, links, active tab |
| `accent-soft` | `#EEE9FD` | selected pill, soft button |
| `accent-chart` | `#8B6CF0` | accent bars |
| `ok-ink / ok-soft / ok-chart / ok-border` | `#0B7A53 / #E2F4EB / #22B07D / #BFE6D2` | on target, passed |
| `warn-ink / warn-soft / warn-chart / warn-border` | `#A35200 / #FDF1DC / #F2A93B / #F4D9A8` | tight, pending |
| `bad-ink / bad-soft / bad-chart / bad-border` | `#BE1E48 / #FCE7ED / #EC5B7E / #F3C3D0` | late, failed, blocked |
| `plan-ink / plan-soft / plan-chart` | `#4D4868 / #EFEDF5 / #C9C2E2` | target, plan, neutral |

Tile backgrounds for status KPIs: ok `#F5FBF8`, warn `#FFFAF1`, bad `#FFF6F8`.

## Type

- Sans: **Inter** 400/500/600/700. Page title 28/700, section 18/600, body 14/400.
- Mono: **JetBrains Mono** 400/500/600 — all numbers, document refs (`GO/2026/0031`), labels.

## Shape

Radius 10 controls · 12 tiles · 14–16 panels · 999 pills. Shadow `0 1px 2px rgba(27,24,48,.06)` floating only.

## Status rules (apply everywhere)

| Ratio / state | Status |
|---|---|
| output ≥ target, load ≤ 90%, passed, on time | ok |
| 90% ≤ output < 100%, load 90–100%, pending, tight vs ex-factory | warn |
| output < 90%, load > 100%, failed, late | bad |
| plan, target, neutral counts | plan / plain surface |

## Dark ("night shift") theme

The reference app offers a per-user day/night toggle. We ship light first; a dark token set can be added later
by overriding the same CSS custom properties under `.o_zg_dark`.
