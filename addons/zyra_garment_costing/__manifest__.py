{
    "name": "Zyra Garment — Costing",
    "version": "18.0.1.0.0",
    "summary": "Versioned garment cost sheets: material, trims, processes, making cost, "
               "FOB price, margin floor with Factory Manager approval",
    "description": "Garment cost sheets for the Zyra garment ERP. See README.md for the contract other "
                   "modules rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": ["zyra_techpack", "purchase", "sale"],
    "data": [
        "security/zyra_garment_costing_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "wizard/cost_sheet_approve_wizard_views.xml",
        "wizard/cost_sheet_whatif_views.xml",
        "views/garment_cost_sheet_views.xml",
        "views/zyra_techpack_views.xml",
        "report/cost_sheet_report.xml",
        "views/menus.xml",
    ],
    "demo": [
    ],
    "installable": True,
}
