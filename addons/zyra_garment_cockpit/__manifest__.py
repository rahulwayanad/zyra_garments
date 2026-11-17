{
    "name": "Zyra Garment — Cockpits",
    "version": "18.0.1.0.0",
    "summary": "One cockpit per department: KPI tiles, charts and lists that click through to the records",
    "description": "Department cockpits for the Zyra garment ERP. See README.md.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_theme",
        "zyra_garment_merch",
        "zyra_garment_costing",
        "zyra_garment_materials",
        "zyra_garment_cutting",
        "zyra_garment_sewing",
        "zyra_garment_jobwork",
        "zyra_garment_quality",
        "zyra_garment_shipping",
        "zyra_garment_wages",
        "zyra_garment_pnl",
    ],
    "data": [
        "views/cockpit_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_garment_cockpit/static/src/cockpit/*",
        ],
    },
    "installable": True,
}
