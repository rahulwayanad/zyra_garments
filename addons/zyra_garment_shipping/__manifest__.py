{
    "name": "Zyra Garment — Packing & Shipping",
    "version": "18.0.1.0.0",
    "summary": "Pack plans, cartons with SSCC-18 labels, shipments through stock pickings, "
               "letters of credit and the printed packing list",
    "description": "Packing and shipping for the Zyra garment ERP. See README.md for the models, "
                   "rules and what other modules can rely on.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_merch",
        "zyra_garment_theme",
        "stock",
        "account",
        "mrp",
    ],
    "data": [
        "security/zyra_garment_shipping_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "report/shipping_reports.xml",
        "report/packing_list_report.xml",
        "wizard/garment_carton_pack_wizard_views.xml",
        "wizard/garment_shipment_override_wizard_views.xml",
        "wizard/garment_lc_amend_wizard_views.xml",
        "views/garment_pack_plan_views.xml",
        "views/garment_carton_views.xml",
        "views/garment_shipment_views.xml",
        "views/garment_lc_views.xml",
        "views/garment_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/shipping_demo.xml",
    ],
    "installable": True,
}
