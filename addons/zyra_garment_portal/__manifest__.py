{
    "name": "Zyra Garment — Buyer and Vendor Portal",
    "version": "18.0.1.0.0",
    "summary": "Buyers follow their orders, styles and T&A and approve samples and lab dips; "
               "job-work vendors see the jobs they hold",
    "description": "Buyer and job-work vendor portal for the Zyra garment ERP. See README.md for the pages, "
                   "record rules and what other modules can rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "portal",
        "zyra_garment_merch",
        "zyra_garment_shipping",
        "zyra_garment_jobwork",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/portal_security.xml",
        "views/portal_templates.xml",
    ],
    "demo": [
        "demo/portal_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "zyra_garment_portal/static/src/scss/portal.scss",
        ],
    },
    "installable": True,
}
