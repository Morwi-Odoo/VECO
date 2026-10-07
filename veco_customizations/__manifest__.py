# -*- coding: utf-8 -*-
# © 2020 Morwi Encoders Consulting SA DE CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    'name': 'Veco Customizations',
    'version': '2.0.3',
    'author': 'Morwi Encoders Consulting SA DE CV',
    'category': 'Hidden',
    'website': 'http://www.morwi.mx/',
    'license': 'LGPL-3',
    'summary': 'Specific customizations for Veco',
    'depends': [
        'l10n_mx_edi',
        'hr_expense',
        'sale',
        'purchase',
        'mrp_workorder',
        'mrp_account_enterprise',
        'purchase_request',
        'stock_account',
    ],
    'data': [
        'views/mrp_production_views.xml',
        'views/purchase_request_views.xml',
    ]
}
