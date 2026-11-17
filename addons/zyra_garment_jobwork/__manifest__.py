{
    "name": "Zyra Garment — Job Work",
    "version": "18.0.1.0.0",
    "summary": "Outsourced sewing, wash, print and embroidery with delivery challans, "
               "process loss and billing at the agreed rate",
    "description": "Job work (outsourced processes) for the Zyra garment ERP. See README.md for the models, "
                   "rules and what other modules can rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_cutting",
        "zyra_garment_theme",
        "purchase",
        "stock",
    ],
    "data": [
        "security/zyra_garment_jobwork_security.xml",
        "security/ir.model.access.csv",
        "data/jobwork_data.xml",
        "report/delivery_challan_report.xml",
        "views/garment_jobwork_order_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
