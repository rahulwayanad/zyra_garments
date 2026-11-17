{
    "name": "Zyra Garment — Wages",
    "version": "18.0.1.0.0",
    "summary": "Piece-rate wage sheets from coupon scans, minimum-wage top-up, overtime, incentive, journal entry",
    "description": "Operator wages for the Zyra garment ERP. See README.md.",
    "author": "Pearlsoft Technologies",
    "category": "Manufacturing/Garment",
    "license": "OPL-1",
    "depends": ["zyra_garment_sewing", "hr", "account"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "report/wage_slip.xml",
        "views/wage_views.xml",
    ],
    "demo": ["demo/wages_demo.xml"],
    "installable": True,
}
