# -*- coding: utf-8 -*-

{
    "name": "Payroll Multicompany",
    "description": """
    Added mutlti company filter in Payroll models.
    """,
    "version": "15.01",
    "author": "IT Admin",
    "website": "",
    "category": "Hidden",
    "depends": ["hr_payroll", "nomina_cfdi_ee"],
    "data": [
         #    "security/security.xml",
             "views/hr_payslip_view.xml",
    ],
    "demo": [
        
    ],
    "installable": True,
    'license': 'AGPL-3',
}
