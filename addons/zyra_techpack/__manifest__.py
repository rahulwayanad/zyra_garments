{
    "name": "Zyra Tech Pack",
    "version": "18.0.2.0.0",
    "summary": "Garment styles with versioned tech packs: BOM per colourway and size, graded measurement "
               "spec, construction, operation bulletin, Odoo BOM, sale and manufacturing gates",
    "description": "Style master and versioned tech packs of the Zyra garment ERP. "
                   "See README.md for the contract other modules rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": ["zyra_garment_base", "mrp", "sale_management", "sale_mrp"],
    "data": [
        "security/zyra_techpack_security.xml",
        "security/ir.model.access.csv",
        "views/garment_style_views.xml",
        "views/zyra_techpack_views.xml",
        "views/product_views.xml",
        "views/sale_mrp_views.xml",
        "report/zyra_techpack_report.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/zyra_techpack_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "zyra_techpack/static/src/scss/zyra_techpack.scss",
        ],
    },
    "application": False,
    "installable": True,
}
