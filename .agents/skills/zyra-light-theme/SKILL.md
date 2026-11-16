---
name: zyra-light-theme
description: Apply the Zyra light theme to Odoo 18 garment screens — design tokens as CSS custom properties, where the SCSS goes in the asset bundles, KPI tile / status / cockpit / floor-screen patterns, and accessibility rules. Use when building any view, OWL component, cockpit, report styling or floor screen (scan station, tablet inspection, TV board, planning board).
---

# Zyra light theme in Odoo 18

**Binding design: `.agents/docs/design/screens/` (125 screen images).** Build every screen exactly as its image —
layout, labels, columns, order, colours. Where this skill, `tokens.scss` or light-theme.md disagree with an image,
the image wins. Rules: `.agents/docs/design/screens/README.md` → "Build strictly as designed".

Design spec and mockups: `.agents/docs/design/light-theme.md` and `.agents/docs/design/mockups/*.dc.html`
(live canvas: https://claude.ai/artifact/V5fPbqrDv1kJZf6gwNuCVt). Tokens file: `tokens.scss` next to this skill.

## Where the code goes

- `zyra_garment_base` owns the theme. Copy `tokens.scss` to
  `zyra_garment_base/static/src/scss/zg_tokens.scss` and add a `zg_components.scss` for shared classes.
- Register in base `__manifest__.py`:

```python
"assets": {
    "web.assets_backend": [
        "zyra_garment_base/static/src/scss/zg_tokens.scss",
        "zyra_garment_base/static/src/scss/zg_components.scss",
        "zyra_garment_base/static/src/fonts/fonts.scss",   # self-host Inter + JetBrains Mono (no Google CDN on the floor)
    ],
    "web.assets_frontend": [  # portal
        "zyra_garment_base/static/src/scss/zg_tokens.scss",
        "zyra_garment_base/static/src/scss/zg_components.scss",
    ],
    "web.report_assets_common": [
        "zyra_garment_base/static/src/scss/zg_report.scss",
    ],
},
```

- Other modules **use** the classes and `var(--zg-*)` properties; they never redefine colours.
- Scope everything under `.o_zg` (add `class="o_zg"` on our OWL roots and `<form class="o_zg">` /
  `<list class="o_zg">` views) so standard Odoo screens keep Odoo's look. Recolouring all of Odoo is a separate,
  explicit decision (via `web._assets_primary_variables`), not the default.
- Fonts: self-host woff2 files in `static/src/fonts` — factory floor networks are often offline.

## Patterns

**KPI tile** — label (mono 11px uppercase, muted, status dot) above a mono value; tile tinted by status.

```xml
<div class="o_zg_kpi o_zg_kpi--bad">
  <span class="o_zg_kpi__label"><span class="o_zg_dot"/>EX-FACTORY IN</span>
  <span class="o_zg_kpi__value">−2 d</span>
</div>
```

Status modifiers: `--ok`, `--warn`, `--bad`, none = neutral. Status thresholds: light-theme.md › Status rules.
Compute the status in Python (`fields.Selection([('ok','On target'),('warn','Tight'),('bad','Late')])`) so lists,
cockpits and portal all agree; the view only maps it to a class (`decoration-success/warning/danger` in lists).

**Status pill** — `<span class="o_zg_pill o_zg_pill--ok">PASSED</span>`.

**Cockpit** — OWL client action: header (icon, eyebrow, title, subtitle, actions) → **one sentence naming the worst
thing** (`o_zg_headline`, offending entity in `--zg-bad-ink`) → KPI rail (`o_zg_kpi_rail`, auto-fit grid) →
filter bar (period pills, scope) → chart cards. Every chart card has a table toggle and CSV export.
Charts: Odoo's bundled Chart.js; colours from tokens — target/plan bars `--zg-plan-chart`, output bars by status
`--zg-*-chart`, line series `--zg-accent`, target line dashed `--zg-warn-ink`.

**Forms** — smart buttons as bordered chips with mono count; status bar as a pill group (active = accent-soft);
group headings mono 12px accent; field labels mono 11px muted.

**Floor screens** (scan station, inspection tablet, TV board): `o_zg_floor` root → 44px+ targets, primary input
72px tall with 28px mono text, autofocus kept on the scan input, connection pill (Online · n queued / Offline ·
n queued), last scans list (ok rows soft-green, refused rows soft-rose with the reason).

**Planning board** — grid with day columns; bars coloured soft fill + 1.5px status border; clash = white fill with
dashed warn border; weekly load bar under each line (ok ≤90%, warn 90–100%, bad >100%).

## Accessibility (non-negotiable)

- Text ≥4.5:1 — only `*-ink` colours as text on white; `*-chart` colours are for bars/dots only.
- Status never by colour alone: always a word or number too (PASSED, 71%, −2 d).
- Real `<button>`, `<a>`, `<input>` with `<label>`; `aria-label` on icon-only buttons.
- Touch targets ≥44px on floor screens.

## Don't

- No gradients, glows or neon from the reference app's dark theme. Borders, not shadows.
- No emoji icons — use Odoo's `fa` icons or inline stroke SVG.
- No reference-app screenshots, icons or copy in our code (skill `reference-app`).
