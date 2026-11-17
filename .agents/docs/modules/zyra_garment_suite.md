# zyra_garment_suite — spec

Status: built (17 Nov 2026, on Rahul's request "create a module for all as a single app: garment suite")
Build day: after wave 5 · Depends on: every merged zyra_* module

## Scope
One installable app, **Garment Suite**, that installs the whole Zyra garment ERP in a single step. It holds no
models or screens of its own: its manifest depends on every merged module, so installing it pulls in all of
them. It is the only Zyra module marked as an application, so the Apps list shows one card instead of fifteen.
The shared top menu (owned by `zyra_garment_base`) is named **Garment Suite** to match.

Not in scope: any business logic, views or data. Those stay in the area modules.

## Modules it installs
zyra_garment_theme, zyra_garment_base, zyra_techpack, zyra_garment_costing, zyra_garment_merch,
zyra_garment_materials, zyra_garment_cutting, zyra_garment_jobwork, zyra_garment_quality, zyra_garment_sewing,
zyra_garment_wages, zyra_garment_shipping, zyra_garment_pnl, zyra_garment_portal, zyra_garment_connect,
zyra_garment_cockpit.

## Changes outside this module
- `zyra_garment_base`: `application` → False (the suite is the app); root menu `menu_garment_root` renamed
  "Garment" → "Garment Suite". The menu stays in base so every module keeps its parent.

## Business rules → tests
- [x] `test_installing_suite_installs_every_garment_module`
- [x] `test_suite_is_the_only_garment_application`
- [x] `test_top_menu_is_named_garment_suite`

## Screens
None of its own.

## Open questions
- None.
