# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class hr_employee(models.Model):
    _inherit = 'hr.employee'

    loan_request = fields.Integer('Solicitud del prestamo por año', default=1, required=True)
    no_employee = fields.Char('No de empleado')

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    loan_request = fields.Integer('Solicitud del prestamo por año', default=1, required=True)
    no_employee = fields.Char('No de empleado')
