{
    "name": "Zyra Garment — Order P&L",
    "version": "18.0.1.0.0",
    "summary": "Profit and loss of every production order: invoiced revenue against planned and actual cost",
    "description": "Order P&L for the Zyra garment ERP. See README.md.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": [
        "zyra_garment_costing",
        "zyra_garment_shipping",
        "zyra_garment_jobwork",
        "zyra_garment_wages",
        "stock_account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/pnl_security.xml",
        "data/pnl_cron.xml",
        "views/pnl_views.xml",
    ],
    "demo": ["demo/pnl_demo.xml"],
    "installable": True,
}
