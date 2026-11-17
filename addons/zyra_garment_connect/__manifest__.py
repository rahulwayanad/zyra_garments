{
    "name": "Zyra Garment — Connect",
    "version": "18.0.1.0.0",
    "summary": "REST API with scoped keys, signed webhooks, CSV import with dry run",
    "description": "API keys, JSON REST API under /api/garment/v1, HMAC-signed webhooks and CSV imports with a "
                   "dry run for the Zyra garment ERP. See README.md.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": ["zyra_garment_base", "zyra_garment_merch", "zyra_garment_theme", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "security/connect_security.xml",
        "data/connect_data.xml",
        "views/garment_api_key_views.xml",
        "views/garment_webhook_views.xml",
        "views/garment_import_views.xml",
        "views/garment_connect_cockpit_views.xml",
        "views/menus.xml",
    ],
    "demo": ["demo/connect_demo.xml"],
    "installable": True,
}
