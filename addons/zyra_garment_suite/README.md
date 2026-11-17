# Garment Suite (`zyra_garment_suite`)

Install this one app to get the whole Zyra garment ERP. It has no models or screens of its own; its manifest
depends on every Zyra module, and it is the only Zyra module shown as an app.

The top menu **Garment Suite** is defined in `zyra_garment_base` (`menu_garment_root`) so every module can hang
its menus under it.

When a new Zyra module is merged, add it to `depends` here (the test
`test_installing_suite_installs_every_garment_module` fails if an installed `zyra_*` module is missing).
