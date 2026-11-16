# Zyra Garment ERP — Odoo 18 Community

Fifteen Odoo 18 CE modules that run a cut-and-sew garment factory from tech pack to export carton.
Owner: Rahul. Build 17–20 Nov 2026 with Claude Code; pilot go-live 14 Dec 2026; full go-live 11 Jan 2027.

All project knowledge lives in **`.agents/`** (docs + skills). `AGENTS.md` is a symlink to this file and
`.claude/skills` is a symlink to `.agents/skills`. **Build plan: `.agents/zyra_build_kit/build_prompts.md`**
(5 waves, one prompt per module — the model/field/xml-id names in it are a contract). Progress:
`.agents/build-progress.md`.

## Always loaded

@.agents/docs/project-plan.md
@.agents/build-progress.md

## Read when relevant

| When | Read |
|---|---|
| Building a module | its prompt in `.agents/zyra_build_kit/build_prompts.md` + READMEs of the modules it depends on |
| Odoo 18 workflow, tests | skill `odoo18-module-dev` |
| Business rules, formulas, glossary | skill `garment-domain` |
| Any screen | `docs/screens/sNNN.jpg` + `docs/screens/captions.json` (binding); skill `zyra-light-theme` |
| Reference app (clean-room) | skill `reference-app`, `.agents/docs/reference/feature-reference.md` |
| Module layout overview | `.agents/docs/architecture.md` (kit prompts win where they differ) |

## Layout
- `addons/<module>/` — one module per department. Prefix `zyra_garment_` (`zyra_techpack` keeps its name).
- `docs/screens/sNNN.jpg` + `captions.json` — the target screens. Match their fields, states, KPIs, layout,
  labels, columns and order; nothing added or dropped. Image beats any theme doc.
- `docs/requests/<module>.md` — need a change in a module you don't own? Write it here. Never edit that module.
- `odoo18/` — Odoo 18.0 source + `venv/` (Python 3.12). Not in git.

## Ownership
Only edit the module named in your prompt. Read any other module freely.

## Odoo 18 rules
- `<list>` not `<tree>`; `invisible="…"`/`readonly="…"` expressions, no attrs/states; `<chatter/>` in forms.
- Kanban: `<t t-name="card">` with aside/main/footer.
- `res.users.groups_id`; product type: `is_storable`; Command API for x2many; `copy_data` returns a list.
- `group_expand` for kanban columns; `_read_group` for aggregates.
- Every model: `_description`, `ir.model.access` rows per role, record rules for multi-company.
- Translations: `_()` with `self.env`, never at module level.
- Money in company currency with `currency_id`; quantities with product UoM.

## Look
Depend on `zyra_garment_theme`. Use its classes: `.o_zyra_kpis` / `.o_zyra_kpi` (`_good/_warn/_bad/_text`)
for header KPI tiles, section headers, pill statusbar. Light theme only, no dark screens. (This settles the
earlier theme question: `zyra_garment_theme` is the theme; the `zyra-light-theme` skill's `.o_zg` tokens are
reference only.)

## Menus
Hang menus under the roots from `zyra_garment_base` (`menu_garment_root` and its section menus).

## Tests and environment
```bash
cd /home/rahul/Personal/Garnaments            # or the worktree root
O=/home/rahul/Personal/Garnaments/odoo18
$O/venv/bin/python $O/odoo-bin -c $O/odoo.conf --logfile= \
  --addons-path=$O/addons,$O/odoo/addons,$PWD/addons --db-filter='.*' -d zyra_<module> \
  -i <module> --test-tags=/<module> --stop-after-init --log-level=test 2>&1 | tail -80
```
DB credentials come from `odoo18/odoo.conf` (never copy the password into tracked files). Use one DB per
module (`zyra_<module>`); drop it for a clean install:
`PGPASSWORD=$(grep -Po '^db_password = \K.*' $O/odoo.conf) dropdb -h localhost -U odoo --if-exists zyra_<module>`.
`odoo.conf` sets `without_demo = all`: pass `--without-demo=` (empty) when demo data is needed. Demo data is loaded (no
`--without-demo`). Never touch the `garments` DB or other databases on this server.

A module is done only when it installs on an empty DB, all tests pass, and there are no warnings in the log.

## Done means
Installs clean · tests green · demo data shows every screen in your prompt · README.md in the module with
models, menus, and what other modules can rely on.

## Non-negotiable
1. Odoo 18 Community only. 2. Clean-room: never copy mn_garment code, names of its files, text, data or images;
invented demo names only. 3. Tests name the rule they check. 4. Out of scope until after go-live: decoration /
team wear, compliance, made-to-measure (screens 18–19, 82–113), AI document reading is optional only.
5. Decisions go into `.agents/docs/` or the module README, not only chat.
