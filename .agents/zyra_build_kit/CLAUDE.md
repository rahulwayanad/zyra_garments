# Zyra Garment ERP — rules for every session

Stack: Odoo 18 Community, Python 3.11+, PostgreSQL. Clean-room build: mn_garment (Odoo 19, OPL-1) is a
functional reference only. Never copy its code, names of its files, or its text.

## Layout
- addons/<module>/ — one module per department. Prefix: zyra_garment_ (zyra_techpack keeps its name).
- docs/screens/sNNN.jpg + captions.json — the target screens. Match their fields, states and KPIs.
- docs/requests/<module>.md — if you need a change in a module you don't own, write it here. Never edit it.

## Ownership
Only edit the module named in your prompt. Read any other module freely.

## Odoo 18 rules
- <list> not <tree>; invisible="…"/readonly="…" expressions, no attrs/states; <chatter/> in forms.
- Kanban: <t t-name="card"> with aside/main/footer.
- res.users.groups_id; product type: is_storable; Command API for x2many; copy_data returns a list.
- group_expand for kanban columns; _read_group for aggregates.
- Every model: _description, ir.model.access rows per role, record rules for multi-company.
- Translations: _() with self.env, never at module level.
- Money in company currency with currency_id; quantities with product UoM.

## Look
Depend on zyra_garment_theme. Use its classes: .o_zyra_kpis / .o_zyra_kpi (_good/_warn/_bad/_text)
for header KPI tiles, section headers, pill statusbar. Light theme only, no dark screens.

## Menus
Hang menus under the roots from zyra_garment_base (menu_garment_root and its section menus).

## Tests
Each module ships tests/ with TransactionCase tests for every state change and every computed figure.
Run: python odoo-bin -d zyra_<module> --addons-path=<odoo>/addons,addons \
     -i <module> --test-tags=/<module> --stop-after-init
A module is done only when it installs on an empty DB, all tests pass, and there are no warnings in the log.

## Done means
Installs clean · tests green · demo data shows every screen in your prompt · README.md in the module
with models, menus, and what other modules can rely on.
