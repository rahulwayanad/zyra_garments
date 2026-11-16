{
    'name': 'Zyra Garment Light Theme',
    'version': '18.0.1.0.0',
    'summary': 'Light backend theme for the Zyra garment modules: white cards, violet accent, '
               'KPI tiles, uppercase section headers and pill status bars',
    'author': 'Pearlsoft Technologies',
    'category': 'Hidden/Theme',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        # Prepended so our values win over Odoo's !default variables.
        'web._assets_primary_variables': [
            ('prepend', 'zyra_garment_theme/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'zyra_garment_theme/static/src/scss/theme.scss',
        ],
    },
    'installable': True,
}
