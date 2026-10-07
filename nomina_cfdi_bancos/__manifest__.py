# -*- coding: utf-8 -*-
{
    "name": "Nomina CFDI bancos",
    "author": "IT Admin",
    "version": "19.1.0",
    "category": "Other",
    "description":"Genera dispersion de bancos para la nómina.",
    "depends": ["nomina_cfdi_ee",'hr_payroll','hr'],
    "data": [
        'security/ir.model.access.csv',
        "wizard/generar_pagos_banco.xml",
        "views/hr_employee_view.xml",
    ],
    "license": 'AGPL-3',
    'installable': True,
    'images': [''],
}
