---
name: odoo18-module-dev
description: How to build, test and merge one Zyra garment module on Odoo 18 Community — the spec → write → prove → merge loop, Odoo 18 API rules (list views, invisible expressions, chatter, create_multi), module layout, security, tests and the daily install gate. Use whenever creating or changing any zyra_* module.
---

# Building a Zyra module on Odoo 18 CE

Read first: `.agents/docs/project-plan.md` (the loop and the days) and `.agents/docs/architecture.md`
(module names, dependencies, Odoo touch-points).

## The loop — every module, no exceptions

1. **Spec.** Before code, write `.agents/docs/modules/<module>.md`: scope, models + key fields, business rules
   (each phrased as a sentence that becomes a test name), screens, printed documents, the reference screens used
   (page numbers from `.agents/docs/reference/screenshots-index.md`), and what is out of scope. Confirm with Rahul.
2. **Write** in its own git worktree / branch `module/<name>`: models, security, views, reports, demo data, tests.
3. **Prove.** Install on a real Odoo 18 + PostgreSQL database, run tests, open every menu and form in a browser,
   fix what fails. "It compiles" is not proof.
4. **Merge** only when the module installs on a fresh DB together with everything already merged and all tests pass.
5. **Review** — evening walkthrough with Rahul + functional consultant; fixes go to the next morning's list.

**Daily gate:** fresh DB, install every merged module together, all tests green. Never carry red into the next day.

## Module layout

```
zyra_garment_<area>/
  __init__.py
  __manifest__.py
  models/            one file per model, __init__.py imports all
  security/
    zyra_garment_<area>_security.xml   groups (only in base) & record rules
    ir.model.access.csv                every model, every role
  views/             <model>_views.xml, menus.xml (menus last in manifest)
  report/            QWeb reports + paperformat
  data/              sequences, default data (noupdate="1")
  demo/              demo data: invented names only
  static/src/        OWL components, SCSS (see skill zyra-light-theme)
  tests/             test_<rule_area>.py
```

Manifest:

```python
{
    "name": "Zyra Garment — <Area>",
    "version": "18.0.1.0.0",
    "category": "Manufacturing/Garment",
    "depends": ["zyra_garment_base", ...],
    "data": [  # order matters: security → data → views → reports → menus
    ],
    "demo": [],
    "assets": {"web.assets_backend": ["zyra_garment_<area>/static/src/**/*"]},
    "license": "OPL-1",   # confirm with Rahul; modules are meant to be sellable
    "installable": True,
}
```

Naming: models `zyra.garment.<thing>` (techpack keeps its existing `zyra.techpack.*`), XML ids
`<model_underscored>_view_form`, sequences `GO/%(year)s/` style refs (e.g. `GO/2026/0031` production order).

## Odoo 18 rules (the usual mistakes)

- Views: **`<list>`** not `<tree>`; `view_mode="list,form"`.
- **No `attrs` / `states`.** Use expressions: `invisible="state != 'draft'"`, `readonly="..."`, `required="..."`.
- Chatter: `<chatter/>` at the end of the form (model inherits `mail.thread`, `mail.activity.mixin`).
- `name_get` is gone → `_compute_display_name`; searching → `_rec_names_search`.
- `create` overrides use `@api.model_create_multi` and take a list of vals.
- Multi-company: `_check_company_auto = True`, `check_company=True` on relational fields, `company_id` on records.
- Money: `fields.Monetary(currency_field="currency_id")`.
- Lots: `stock.lot` (not `stock.production.lot`). Manufacturing: `mrp.production`. Journal entries: `account.move`.
- Size × colour grid on orders: reuse product variants + `sale_product_matrix` / `purchase_product_matrix` (CE).
- Translations: wrap user-facing strings with `_()` / `self.env._()`.
- `fields.Selection` additions in inherits use `selection_add` with `ondelete`.
- Computed stored fields: list every dependency in `@api.depends`; avoid `depends` on `id`.
- Constraints: `@api.constrains` raising `ValidationError` with a sentence a user understands.
- OWL 2 client actions: `import { Component, useState } from "@odoo/owl"`,
  `registry.category("actions").add("zyra_<tag>", Comp)`, template `static template = "module.Name"` in an XML
  under `static/src`.
- Controllers for API/portal: `odoo.http.Controller`, `@http.route(..., auth="user"|"public"|"none", type="json"|"http")`;
  portal extends `CustomerPortal._prepare_home_portal_values`.

## Security

- Groups and the 11 roles live **only in `zyra_garment_base`**; other modules reference them.
- Every new model gets lines in `ir.model.access.csv` for every role that needs it (Viewer = read only).
- Record rules for multi-company and for vendor/buyer portal users (see only their own records).
- Approvals and overrides (margin floor, shipping a blocked lot, LC late) → Factory Manager only, logged in chatter.

## Tests

- `from odoo.tests import TransactionCase, HttpCase, Form, tagged`
- `@tagged("post_install", "-at_install", "zyra")` on every class.
- One test per business rule; the **method name states the rule**:
  `test_failed_final_inspection_blocks_shipment`, `test_cost_sheet_below_margin_floor_needs_manager_approval`.
- Use `Form(...)` to exercise onchanges like a user would.
- Floor screens: one `HttpCase` tour per OWL screen (scan station, planning board, inspection tablet).

Commands (adjust paths to the local Odoo 18 checkout / container):

```bash
# install + test one module on a throwaway DB
odoo-bin -c odoo.conf -d zg_test_<area> -i zyra_garment_<area> --test-enable --test-tags /zyra_garment_<area> --stop-after-init --log-level=test
# daily gate: fresh DB, everything merged
odoo-bin -c odoo.conf -d zg_gate_$(date +%F) -i zyra_garment_base,zyra_techpack,... --test-enable --test-tags zyra --stop-after-init
```

A run is green only if the log has no `ERROR`/`FAIL` lines and the module state is `installed`.

## Prove in the browser

After tests pass: start the server on the test DB, log in as each relevant role, open every menu of the module,
create one record per form through the UI, print every report. Note anything broken and fix before merge.

## Demo data

Invented companies, buyers and people only (never names from the reference app). Each module adds demo that
continues the shared demo order so Day 4 can run one order tech pack → shipped cartons.

## Clean-room

Never paste or retype code, labels, help text or images from the reference app. Reason from the feature
description (`.agents/docs/reference/feature-reference.md`) and design our own. See skill `reference-app`.
