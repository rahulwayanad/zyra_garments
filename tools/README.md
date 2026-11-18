# Tools

## `install_garment_demo.sh` — one command: new DB with the garment demo only

```bash
tools/install_garment_demo.sh garments_demo            # refuses if the DB exists
tools/install_garment_demo.sh garments_demo --drop     # drop it (and its filestore) first
tools/install_garment_demo.sh garments_demo --tz Asia/Dubai
```

Creates the DB without any demo, installs `zyra_garment_suite`, runs `load_garment_demo.py` (below), then sets the
admin timezone (default `Asia/Kolkata`) so the browser cannot store the legacy alias `Asia/Calcutta`, which
PostgreSQL without `tzdata-legacy` rejects in by-day groupings. Odoo is found at `$ODOO_PATH`, else `<repo>/odoo18`,
else `<repo>/../odoo-18`; config `$ODOO_CONF` (default `$ODOO_PATH/odoo.conf`). Refuses the shared `garments` DB.

## `load_garment_demo.py` — garment demo only

Fills a database with the Zyra garment demo (invented buyers, styles, orders, rolls, bundles, wages, the full-sale
story) and **none of Odoo's own demo** (no Azure Interior, Deco Addict, Mitchell Admin, office-furniture products).

```bash
O=/home/rahul/Personal/Garnaments/odoo18
# 1. create the database WITHOUT demo (odoo.conf has without_demo = all) and install the suite
$O/venv/bin/python $O/odoo-bin -c $O/odoo.conf -d garments_demo -i zyra_garment_suite --stop-after-init
# 2. load the garment demo of every installed zyra_* module, in dependency order
$O/venv/bin/python tools/load_garment_demo.py -c $O/odoo.conf -d garments_demo
```

- Uses Odoo's own demo loader per module (noupdate, demo mode) and marks those modules as having demo.
- Refuses a database that already has Odoo's demo, or the garment demo already.
- Odoo source is found at `$ODOO_PATH`, else `<repo>/odoo18`. Pass `--addons-path` when running from a worktree.
- Works because garment demo files only refer to standard non-demo records (countries, admin user, main company,
  groups, units of measure).

**Production:** never run this. A production database is created with `without_demo = all` and gets no demo at
all; Odoo then never loads demo for modules installed later either (demo needs every parent module to have it).
