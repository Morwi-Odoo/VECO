# -*- coding: utf-8 -*-

from odoo import api, models, fields, _


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    dias_pagar = fields.Float('Pagar en la nomina', digits=(0, 4))
    imss_dias = fields.Float('Cotizar en el IMSS', default='15', digits=(0, 4))
