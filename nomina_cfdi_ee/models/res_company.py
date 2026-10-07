# -*- coding: utf-8 -*-
import base64
import json
import requests
from odoo import fields, models,api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from dateutil import parser

class ResCompany(models.Model):
    _inherit = 'res.company'

    curp = fields.Char('CURP')
    serie_nomina = fields.Char('Serie nomina')
    nomina_mail = fields.Char('Nomina Mail')
    company_cfdi = fields.Boolean(string="CFDI MX")

    ######################################### Eliminar campos ###################################################
    proveedor_timbrado= fields.Selection(
        selection=[('servidor', _('Principal')),
                   ('servidor2', _('Respaldo')),],
        string=_('Servidor de timbrado'), default='servidor'
    )
    api_key = fields.Char(string=_('API Key'))
    modo_prueba = fields.Boolean(string=_('Modo prueba'))
    regimen_fiscal = fields.Selection(
        selection=[('601', _('General de Ley Personas Morales')),
                   ('603', _('Personas Morales con Fines no Lucrativos')),
                   ('605', _('Sueldos y Salarios e Ingresos Asimilados a Salarios')),
                   ('606', _('Arrendamiento')),
                   ('608', _('Demás ingresos')),
                   ('609', _('Consolidación')),
                   ('610', _('Residentes en el Extranjero sin Establecimiento Permanente en México')),
                   ('611', _('Ingresos por Dividendos (socios y accionistas)')),
                   ('612', _('Personas Físicas con Actividades Empresariales y Profesionales')),
                   ('614', _('Ingresos por intereses')),
                   ('616', _('Sin obligaciones fiscales')),
                   ('620', _('Sociedades Cooperativas de Producción que optan por diferir sus ingresos')),
                   ('621', _('Incorporación Fiscal')),
                   ('622', _('Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras')),
                   ('623', _('Opcional para Grupos de Sociedades')),
                   ('624', _('Coordinados')),
                   ('628', _('Hidrocarburos')),
                   ('607', _('Régimen de Enajenación o Adquisición de Bienes')),
                   ('629', _('De los Regímenes Fiscales Preferentes y de las Empresas Multinacionales')),
                   ('630', _('Enajenación de acciones en bolsa de valores')),
                   ('615', _('Régimen de los ingresos por obtención de premios')),
                   ('625', _('Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas')),
                   ('626', _('Régimen Simplificado de Confianza')),],
        string=_('Régimen Fiscal'), 
    )
    archivo_cer = fields.Binary(string=_('Archivo .cer'))
    archivo_key = fields.Binary(string=_('Archivo .key'))
    contrasena = fields.Char(string=_('Contraseña'))
    nombre_fiscal = fields.Char(string=_('Razón social'))
    saldo_timbres =  fields.Float(string=_('Saldo de timbres'), readonly=True)
    saldo_alarma =  fields.Float(string=_('Alarma timbres'), default=10)
    correo_alarma =  fields.Char(string=_('Correo de alarma'))

    rfc_patron = fields.Char(string=_('RFC Patrón'))
    registro_patronal = fields.Char(string=_('Registro patronal'))
    fecha_csd = fields.Datetime(string=_('Vigencia CSD'), readonly=True)
    estado_csd =  fields.Char(string=_('Estado CSD'), readonly=True)
    aviso_csd =  fields.Char(string=_('Aviso vencimiento (días antes)'), default=14)
    serie_timbrado = fields.Char(string=_('Serie traslado'))
    ################################################################################################################

    @api.onchange('country_id')
    def _get_company_cfdi(self):
        if self.country_id:
            if self.country_id.code == 'MX':
               values = {'company_cfdi': True}
            else:
               values = {'company_cfdi': False}
        else:
            values = {'company_cfdi': False}
        self.update(values)

    @api.model
    def contract_warning_mail_cron(self):
        companies = self.search([('nomina_mail','!=',False)])
        for company in companies:
            employees = self.env['hr.employee'].search([('company_id', '=', company.id), ('active', '=', True)])
            for employee_id in employees:
                first_date = employee_id._get_first_version_date()
                if not first_date:
                   continue
                mod_first_date = first_date.replace(year=datetime.today().date().year)
                if mod_first_date != datetime.today().date():
                    continue
                if company.nomina_mail:
                    mail_values = {
                    'email_to': company.nomina_mail,
                    'subject': 'Aniversario de un empleado',
                    'body_html': 'Esta semana es el aniversario de ' +  employee_id.name + ' en la empresa, revisar ajuste en sueldo creado en incidencias.',
                    'auto_delete': True,
                    }
                    mail = self.env['mail.mail'].create(mail_values)
                    mail.send()
                self.calculate_contract_vacaciones(employee_id)
                self.create_cambio_salario(employee_id)
        return

    @api.model
    def calculate_contract_vacaciones(self, employee_id):
        tablas_cfdi = employee_id.tablas_cfdi_id
        if not tablas_cfdi:
            tablas_cfdi = self.env['tablas.cfdi'].search([],limit=1)
        if not tablas_cfdi:
            return
        first_date = employee_id._get_first_version_date()
        if first_date:
            date_start = first_date
            today = datetime.today().date()
            diff_date = today - date_start
            years = diff_date.days /365.0
            antiguedad_anos = round(years)
        else:
            antiguedad_anos = 0
        if antiguedad_anos < 1.0:
            tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= antiguedad_anos).sorted(key=lambda x:x.antiguedad)
        else:
            tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad <= antiguedad_anos).sorted(key=lambda x:x.antiguedad, reverse=True)
        if not tablas_cfdi_lines:
            return
        tablas_cfdi_line = tablas_cfdi_lines[0]
        today = datetime.today()
        current_year = today.strftime('%Y')
        leave_type = self.env['hr.leave.type'].search([('code', '=', 'VAC'), ('company_id', '=', employee_id.company_id.id)], limit=1)
        if not leave_type:
            leave_type = self.env['hr.leave.type'].search([('code', '=', 'VAC')], limit=1)
            if not leave_type:
                return

        asignacion_obj = self.env['hr.leave.allocation'].create(
              {'name': 'Vacaciones del ' + current_year,
               'holiday_status_id' : leave_type and leave_type.id,
               'date_from' : today,
               'employee_id' : employee_id.id,
               'number_of_days' : tablas_cfdi_line.vacaciones,
              })

        asignacion_obj.action_approve()
        return True

    @api.model
    def create_cambio_salario(self, employee_id):
        first_date = employee_id._get_first_version_date()
        if first_date:
            today = datetime.today().date()
            diff_date = (today - first_date + timedelta(days=1)).days #today - date_start 
            years = diff_date /365.0
            tablas_cfdi = employee_id.tablas_cfdi_id
            if not tablas_cfdi:
                tablas_cfdi = self.env['tablas.cfdi'].search([],limit=1)
            if not tablas_cfdi:
                return
            if years < 1.0:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad >= years).sorted(key=lambda x:x.antiguedad)
            else:
                tablas_cfdi_lines = tablas_cfdi.tabla_antiguedades.filtered(lambda x: x.antiguedad <= years).sorted(key=lambda x:x.antiguedad, reverse=True)
            if not tablas_cfdi_lines:
                return
            tablas_cfdi_line = tablas_cfdi_lines[0]
            sueldo_diario_integrado = ((365 + tablas_cfdi_line.aguinaldo + (tablas_cfdi_line.vacaciones)* (tablas_cfdi_line.prima_vac/100) ) / 365) * employee_id.wage/tablas_cfdi.dias_mes
            if sueldo_diario_integrado > (tablas_cfdi.uma * 25):
                sueldo_base_cotizacion = tablas_cfdi.uma * 25
            else:
                sueldo_base_cotizacion = sueldo_diario_integrado
            incidencia = self.env['incidencias.nomina'].create({'tipo_de_incidencia':'Cambio salario', 
                                                                'employee_id': employee_id.id,
                                                                'sueldo_mensual': employee_id.wage,
                                                                'sueldo_diario': employee_id.sueldo_diario,
                                                                'sueldo_diario_integrado': sueldo_diario_integrado,
                                                                'sueldo_por_horas' : employee_id.sueldo_hora,
                                                                'sueldo_cotizacion_base': sueldo_base_cotizacion,
                                                                'fecha': today,
                                                                })
        return
