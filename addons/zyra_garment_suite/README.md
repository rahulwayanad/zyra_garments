# Garment Suite (`zyra_garment_suite`)

Install this one app to get the whole Zyra garment ERP. It has no models or screens of its own; its manifest
depends on every Zyra module, and it is the only Zyra module shown as an app.

The top menu **Garment Suite** is defined in `zyra_garment_base` (`menu_garment_root`) so every module can hang
its menus under it.

When a new Zyra module is merged, add it to `depends` here (the test
`test_installing_suite_installs_every_garment_module` fails if an installed `zyra_*` module is missing).

## Demo: one full sale (`demo/suite_story_demo.xml` → `models/suite_story_demo.py`)

Loaded after every module's own demo. One new buyer (Coastline Outfitters) and one new style (ST-0201 Organic
Crew Tee, 1,100 pieces in Sage and Optic White) go through every module with the modules' own buttons: tech pack,
fit sample, cost sheet v1 → quotation → buyer counter → v2 approved below the margin floor by the Factory Manager,
sale order → production order with T&A, lab dip / trim card / PP sample, fabric and trims bookings → POs → 10
rolls → 4-point inspection, markers → cut plans → 4 lays → 56 bundles / 672 coupons, print job work (billed on good
pieces), Line 5 with its own USD rate card → 672 coupon scans, inline / end-line / final AQL inspections, pack plan
→ 44 SSCC cartons → stock, LC → shipment → delivery → invoice → payment, posted wage sheet, order P&L, order
completed. Dates run back from the install day. Key records have xml ids `zyra_garment_suite.story_*`.

Step-by-step walkthrough with every figure: `.agents/docs/full-sale-walkthrough.md`.
Tests: `tests/test_full_sale_demo.py` (skipped without demo).

Two demo-only settings, both documented routes: the trims and packing moves of the finished-goods MOs are tagged
`garment_pnl_order_id` (P&L does not read MO moves yet), and the shipment invoice lines get `garment_order_id` and
no tax. Gaps found are filed in `docs/requests/zyra_garment_shipping.md` and `docs/requests/zyra_garment_pnl.md`.
