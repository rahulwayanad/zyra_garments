#!/usr/bin/env python3
"""Load only the Zyra garment demo data — none of Odoo's own demo (no Azure Interior, Mitchell Admin, ...).

The database must have been created WITHOUT demo data (odoo.conf: without_demo = all) and have
zyra_garment_suite installed. The script then loads the `demo` files of every installed zyra_* module, in
dependency order, exactly as Odoo would (noupdate, demo mode), and marks those modules as having demo.

    O=odoo18
    $O/venv/bin/python $O/odoo-bin -c $O/odoo.conf -d mydb -i zyra_garment_suite --stop-after-init
    $O/venv/bin/python tools/load_garment_demo.py -c $O/odoo.conf -d mydb

Run it once. It refuses a database that already has Odoo's demo data or garment demo data.
"""
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# Odoo is a source checkout, not an installed package: use $ODOO_PATH, else <repo>/odoo18
_odoo_src = os.environ.get("ODOO_PATH") or str(Path(__file__).resolve().parents[1] / "odoo18")
if _odoo_src not in sys.path:
    sys.path.insert(0, _odoo_src)

import odoo  # noqa: E402
from odoo.modules.loading import load_data  # noqa: E402
from odoo.modules.module import get_manifest  # noqa: E402
from odoo.tools import config  # noqa: E402

_logger = logging.getLogger("load_garment_demo")


def garment_modules_in_order(env):
    """Installed zyra_* modules, each after the zyra_* modules it depends on."""
    mods = env["ir.module.module"].search([("name", "=like", "zyra\\_%"), ("state", "=", "installed")])
    deps = {m.name: {d.name for d in m.dependencies_id if d.name.startswith("zyra_")} for m in mods}
    order, done = [], set()
    while deps:
        ready = sorted(n for n, d in deps.items() if d <= done)
        if not ready:
            raise SystemExit("Circular dependency between %s" % ", ".join(sorted(deps)))
        for n in ready:
            order.append(n)
            done.add(n)
            del deps[n]
    return order


def main(argv):
    config.parse_config(argv)
    odoo.netsvc.init_logger()
    db = config["db_name"]
    if not db or "," in db:
        raise SystemExit("Give one database with -d.")
    registry = odoo.modules.registry.Registry(db)
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        Module = env["ir.module.module"]
        if Module.search([("name", "=", "base")]).demo:
            raise SystemExit("%s already has Odoo's demo data. Create it with without_demo = all." % db)
        if Module.search_count([("name", "=", "zyra_garment_suite"), ("state", "=", "installed")]) == 0:
            raise SystemExit("Install zyra_garment_suite in %s first." % db)
        loaded = Module.search([("name", "=like", "zyra\\_%"), ("demo", "=", True)])
        if loaded:
            raise SystemExit("Garment demo already loaded in %s (%s)." % (db, ", ".join(loaded.mapped("name"))))
        for name in garment_modules_in_order(env):
            manifest = get_manifest(name)
            if not manifest.get("demo"):
                continue
            _logger.info("Module %s: loading garment demo", name)
            load_data(env, {}, "init", kind="demo", package=SimpleNamespace(name=name, data=manifest))
            cr.execute("UPDATE ir_module_module SET demo = TRUE WHERE name = %s", [name])
            env.invalidate_all()
        cr.commit()
    _logger.info("Garment demo loaded in %s.", db)


if __name__ == "__main__":
    main(sys.argv[1:])
