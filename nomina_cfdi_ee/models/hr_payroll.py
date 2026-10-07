# -*- coding: utf-8 -*-

import base64
import json
import requests
from lxml import etree
import datetime
from datetime import timedelta, date, time
import ast
from pytz import timezone
import math
import urllib.parse
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm
import logging
_logger = logging.getLogger(__name__)
import pytz
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, DEFAULT_SERVER_DATETIME_FORMAT as DTF 
from odoo.tools import float_round
from collections import defaultdict

class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    tipo_cpercepcion = fields.Many2one('nomina.percepcion', string='Tipo de percepción')
    tipo_cdeduccion = fields.Many2one('nomina.deduccion', string='Tipo de deducción')
    tipo_cotro_pago = fields.Many2one('nomina.otropago', string='Otros Pagos')

    category_code = fields.Char("Category Code",related="category_id.code",store=True)

    forma_pago = fields.Selection(
        selection=[('001', 'Efectivo'), 
                   ('002', 'Especie'),],
        string='Forma de pago', default='001')
    exencion = fields.Boolean('Percepción con exención de ISR')
    integrar_al_ingreso = fields.Selection(
        selection=[('001', 'Ordinaria'), 
                   ('002', 'Extraordinaria mensual'),
                   ('003', 'Extraordinaria anual'),
                   ('004', 'Parte exenta por día'),],
        string='Integrar al ingreso gravable como percepción')
#    monto_exencion = fields.Float('Exención (UMA)', digits = (12,3))
    variable_imss = fields.Boolean('Percepción variable para el IMSS')
    variable_imss_tipo = fields.Selection(
        selection=[('001', 'Todo el monto'), 
                   ('002', 'Excedente del (% de UMA)'),
                   ('003', 'Excedente del (% de SBC)'),],
        string='Tipo', default='001')
    variable_imss_monto = fields.Float('Monto')
    integrar_ptu = fields.Boolean('Integrar para el PTU')
    integrar_estatal = fields.Boolean('Integrar para el impuesto estatal')
    parte_gravada = fields.Many2one('hr.salary.rule', string='Parte gravada')
    parte_exenta = fields.Many2one('hr.salary.rule', string='Parte exenta')
    cuenta_especie = fields.Many2one('account.account', 'Cuenta de pago', domain=[('deprecated', '=', False)])
    fondo_ahorro_aux = fields.Boolean('Fondo de ahorro')

class HrPayslip(models.Model):
    _name = "hr.payslip"
    _inherit = ['hr.payslip','mail.thread']


    tipo_nomina = fields.Selection(
        selection=[('O', 'Nómina ordinaria'), 
                   ('E', 'Nómina extraordinaria'),],
        string='Tipo de nómina', required=True, default='O'
    )

    estado_factura = fields.Selection(
        selection=[('factura_no_generada', 'Factura no generada'), ('factura_correcta', 'Factura correcta'), 
                   ('problemas_factura', 'Problemas con la factura'), ('factura_cancelada', 'Factura cancelada')],
        string='Estado de factura',
        default='factura_no_generada',
        readonly=True,
    )
    imss_dias = fields.Float('Cotizar en el IMSS',default='15') #, readonly=True) 
    imss_mes = fields.Float('Dias a cotizar en el mes',default='30') #, readonly=True)

    subsidio_periodo = fields.Float('subsidio_periodo')
    isr_periodo = fields.Float('isr_periodo')
    retencion_subsidio_pagado = fields.Float('retencion_subsidio_pagado')
    importe_imss = fields.Float('importe_imss')
    importe_isr = fields.Float('importe_isr')
    periodicidad = fields.Char('periodicidad')
    concepto_periodico = fields.Boolean('Conceptos periodicos', default = True)
    aplicar_descuentos = fields.Boolean('Aplicar descuentos', default = True)

    #imss empleado
    emp_exedente_smg = fields.Float(string='Exedente 3 SMGDF')
    emp_prest_dinero = fields.Float(string='Prest en dinero')
    emp_esp_pens = fields.Float(string='Gastos médicos')
    emp_invalidez_vida = fields.Float( string='Invalidez y Vida.')
    emp_cesantia_vejez = fields.Float(string='Cesantia y vejez')
    emp_total = fields.Float(string='IMSS trabajador')
    #imss patronal
    pat_cuota_fija_pat = fields.Float(string='Cuota fija patronal')
    pat_exedente_smg = fields.Float(string='Exedente 3 SMGDF.')
    pat_prest_dinero = fields.Float(string='Prest en dinero.')
    pat_esp_pens = fields.Float(string='Gastos médicos.')
    pat_riesgo_trabajo = fields.Float( string='Riegso de trabajo')
    pat_invalidez_vida = fields.Float( string='Invalidez y Vida')
    pat_guarderias = fields.Float(string='Guarderias y PS')
    pat_retiro = fields.Float( string='Retiro')
    pat_cesantia_vejez = fields.Float(string='Cesantia y vejez.')
    pat_infonavit = fields.Float(string='INFONAVIT')
    pat_total = fields.Float(string='IMSS patron')
    fecha_pago = fields.Date('Fecha de pago')
    dias_pagar = fields.Float('Pagar en la nomina')
    ultima_nomina = fields.Boolean(string='Última nómina del mes')
    acum_per_totales = fields.Float('Percepciones totales', readonly=True)
    acum_per_grav  = fields.Float('Percepciones gravadas', readonly=True)
    acum_isr  = fields.Float('ISR', readonly=True)
    acum_isr_antes_subem  = fields.Float('ISR antes de SUBEM', readonly=True)
    acum_subsidio_aplicado  = fields.Float('Subsidio aplicado', readonly=True)
    acum_fondo_ahorro = fields.Float('Acumulado Caja/Fondo ahorro', readonly=True)
    dias_periodo = fields.Float('Dias en el periodo', compute='_get_dias_periodo')
    isr_ajustar = fields.Boolean(string='Ajustar ISR (mensual)')
    acum_sueldo = fields.Float('Sueldo', readonly=True)

    acum_per_grav_anual  = fields.Float('Percepciones gravadas (anual)', readonly=True)
    acum_isr_anual  = fields.Float('ISR (anual)', readonly=True)
    acum_isr_antes_subem_anual  = fields.Float('ISR antes de SUBEM (anual)', readonly=True)
    acum_subsidio_aplicado_anual  = fields.Float('Subsidio aplicado (anual)', readonly=True)
    isr_anual = fields.Boolean(string='ISR anual')
    acum_dev_isr  = fields.Float('Devolución ISR (anual)', readonly=True)
    acum_dev_subem  = fields.Float('Ajuste al SUBEM (anual)', readonly=True)
    acum_dev_subem_entregado  = fields.Float('Ajuste al SUBEM entregado (anual)', readonly=True)
    acum_isr_ajuste  = fields.Float('Ajuste ISR (anual)', readonly=True)

    acum_prima_vac_exento  = fields.Float('Acumulado Prima vacacional exento', readonly=True)

    mes = fields.Selection(
        selection=[('01', 'Enero / Periodo 1'),
                   ('02', 'Febrero / Periodo 2'),
                   ('03', 'Marzo / Periodo 3'),
                   ('04', 'Abril / Periodo 4'),
                   ('05', 'Mayo / Periodo 5'),
                   ('06', 'Junio / Periodo 6'),
                   ('07', 'Julio / Periodo 7'),
                   ('08', 'Agosto / Periodo 8'),
                   ('09', 'Septiembre / Periodo 9' ),
                   ('10', 'Octubre / Periodo 10'),
                   ('11', 'Noviembre / Periodo 11'),
                   ('12', 'Diciembre / Periodo 12'),
                   ],
        string='Mes de la nómina')
    nom_liquidacion = fields.Boolean(string='Nomina de liquidacion', default=False)
    periodicidad_pago = fields.Char(
        'Periodicidad de pago CFDI', compute='_get_periodicidad',
    )
    dias_infonavit = fields.Float('Días INFONAVIT')
    cumpleanos = fields.Boolean('Cumpleaños', compute='_get_cumpleanos', default = False)
    total_nom = fields.Float('Total')
    dias_pagar_incapacidad = fields.Integer("Dias incapacidad a pagar")

    def get_amount_from_rule_code(self, rule_code):
        line = self.env['hr.payslip.line'].search([('slip_id', '=', self.id), ('code', '=', rule_code)])
        if line:
            return round(sum(line.mapped('total')), 2)
        else:
            return 0.0

    def _get_worked_day_lines_values(self, domain=None):
        self.ensure_one()
        if self.country_code != 'MX':
            return super(HrPayslip,self)._get_worked_day_lines_values()
        res = []
        hours_per_day = self._get_worked_day_lines_hours_per_day()

        slip_tz = pytz.timezone(self.version_id.resource_calendar_id.tz)
        utc = pytz.timezone('UTC')
        date_from = slip_tz.localize(datetime.datetime.combine(self.date_from, time.min)).astimezone(utc).replace(tzinfo=None)
        date_to = slip_tz.localize(datetime.datetime.combine(self.date_to, time.max)).astimezone(utc).replace(tzinfo=None)

        work_hours = self.version_id._get_work_hours(date_from, date_to, domain=domain)
        work_hours_ordered = sorted(work_hours.items(), key=lambda x: x[1])
        biggest_work = work_hours_ordered[-1][0] if work_hours_ordered else 0
        add_days_rounding = 0

        # poner en ceros todo
        nb_of_days = (self.date_to - self.date_from).days #+ 1
        leave_days = 0
        inc_days = 0
        vac_days = 0
        factor = 0
        proporcional = 0
        falta_days = 0
        work_data_days = 0
        if self.employee_id.periodicidad_pago == '02' and self.employee_id.septimo_dia:
            if self.employee_id.tipo_semana == '02':
                factor = 7.0/5.0
            elif self.employee_id.tipo_semana == '03':
                factor = 7.0/4.0
            else:
                factor = 7.0/6.0
        if self.employee_id.periodicidad_pago == '04':
            dias_pagar = 15
        elif self.employee_id.periodicidad_pago == '02':
            dias_pagar = 7
        else:
            dias_pagar = (self.date_to - self.date_from).days + 1
        for work_entry_type_id, hours in work_hours_ordered:
            work_entry_type = self.env['hr.work.entry.type'].browse(work_entry_type_id)
            days = round(hours / hours_per_day, 5) if hours_per_day else 0
            if work_entry_type_id == biggest_work:
                days += add_days_rounding
            day_rounded = self._round_days(work_entry_type, days)
            add_days_rounding += (days - day_rounded)
            attendance_line = {
                'sequence': work_entry_type.sequence,
                'work_entry_type_id': work_entry_type_id,
                'number_of_days': day_rounded,
                'number_of_hours': hours,
            }

            #sacar calculos
            if work_entry_type:
                    if work_entry_type.code == 'FJS' or work_entry_type.code == 'FI' or work_entry_type.code == 'FR'  or work_entry_type.code == 'FJC':
                        falta_days += day_rounded * factor
                        leave_days += day_rounded * factor
                        attendance_line.update({'number_of_days': day_rounded * factor})
                        if self.employee_id.septimo_dia:
                            proporcional += (hours / hours_per_day) * factor if hours_per_day else 0
                    elif work_entry_type.code == 'INC_EG' or work_entry_type.code == 'INC_RT' or work_entry_type.code == 'INC_MAT':
                        leave_days += day_rounded
                        if self.employee_id.incapa_sept_dia:
                            inc_days += day_rounded
                    elif work_entry_type.code == 'VAC':
                        if self.employee_id.periodicidad_pago == '04':
                           factor2 = 1
                        else:
                           factor2 = 1.0027
                        vac_days += day_rounded * factor2
                        leave_days += day_rounded * factor2
                        attendance_line.update({'number_of_days': day_rounded * factor2})
                    if work_entry_type.code == 'WORK100':
                        work_data_days = day_rounded
            res.append(attendance_line)

        # ajuste en caso de nuevo ingreso
        nvo_ingreso = False
        date_start_1 = self.employee_id.contract_date_start
        d_from_1 = fields.Date.from_string(self.date_from)
        d_to_1 = fields.Date.from_string(self.date_to)
        if date_start_1 > d_from_1:
            work_data_days =  (self.date_to - date_start_1).days + 1
            nvo_ingreso = True
        if self.employee_id.contract_date_end:
            if d_to_1 > date_start_1:
               work_data_days =  (self.employee_id.contract_date_end - self.date_from).days + 1
               nvo_ingreso = True

        number_of_days = 0
        if work_data_days < 100:
            #periodo para nómina quincenal
               if self.employee_id.periodicidad_pago == '04':
                   if self.employee_id.tipo_pago == '01' and nb_of_days < 17:
                      total_days = work_data_days + leave_days
                      if total_days != 15 or leave_days != 0:
                         if leave_days == 0 and not nvo_ingreso:
                            number_of_days = 15
                         elif nvo_ingreso:
                            number_of_days = work_data_days - leave_days
                         else:
                            number_of_days = 15 - leave_days
                      else:
                         number_of_days = work_data_days
                      if self.employee_id.sept_dia:
                         aux = 2.5
                         number_of_days -=  aux
                         work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','SEPT')])
                         attendances = {
                             'sequence': work_entry_type.sequence,
                             'work_entry_type_id': work_entry_type.id,
                             'number_of_days': aux, 
                             'number_of_hours': round(aux*8,2),
                         }
                         res.append(attendances)
                   elif self.employee_id.tipo_pago == '03' and nb_of_days < 17:
                      total_days = work_data_days + leave_days
                      if total_days != 15.2083 or leave_days != 0:
                         if leave_days == 0  and not nvo_ingreso:
                            number_of_days = 15.2083
                         elif nvo_ingreso:
                            number_of_days = work_data_days * 15.2083 / 15 - leave_days
                         else:
                            number_of_days = 15.2083 - leave_days
                      else:
                         number_of_days = work_data_days * 15.2083 / 15
                      if self.employee_id.sept_dia:
                         aux = 2.21
                         number_of_days -=  aux
                         work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','SEPT')])
                         attendances = {
                             'sequence': work_entry_type.sequence,
                             'work_entry_type_id': work_entry_type.id,
                             'number_of_days': aux, 
                             'number_of_hours': round(aux*8,2),
                         }
                         res.append(attendances)
                   else:
                      dias_periodo = (self.date_to - self.date_from).days + 1
                      total_days = work_data_days + leave_days
                      if total_days != dias_periodo or leave_days != 0:
                         if leave_days == 0  and not nvo_ingreso:
                            number_of_days = dias_periodo
                         elif nvo_ingreso:
                            number_of_days = work_data_days - leave_days
                         else:
                            number_of_days = dias_periodo - leave_days
                      else:
                         number_of_days = work_data_days
               #calculo para nóminas semanales
               elif self.employee_id.periodicidad_pago == '02' and nb_of_days < 8:
                   number_of_days = work_data_days
                ##   if employee_id.septimo_dia: #falta proporcional por septimo día
                   total_days = work_data_days + leave_days
                   if total_days != 7 or leave_days != 0:
                      if leave_days == 0 and not nvo_ingreso:
                         number_of_days = 7
                      elif nvo_ingreso:
                         number_of_days = work_data_days - leave_days
                         if employee_id.sept_dia:
                            number_of_days += 1
                      else:
                         if self.employee_id.work_entry_source != 'attendance':
                            number_of_days = 7 - leave_days
                         else:
                            number_of_days = work_data['days']
                   else:
                      number_of_days = work_data_days
                   if self.employee_id.sept_dia: # septimo día separado
                      if number_of_days == 0:
                         if leave_days != 7:
                            number_of_days = work_data_days
                      if self.employee_id.tipo_semana == '02':
                         aux = number_of_days / 7 * 2
                      elif self.employee_id.tipo_semana == '03':
                         aux = number_of_days / 7 * 3
                      else:
                         aux = number_of_days - int(number_of_days)
                      if aux > 0:
                         number_of_days -=  aux
                      elif number_of_days > 0:
                         if self.employee_id.tipo_semana == '02': # 5 días laborados x 2 de descanso
                            number_of_days -= 2
                            if self.employee_id.incapa_sept_dia:
                               aux = (number_of_days + inc_days + vac_days) / 5
                            else:
                               if self.employee_id.septimo_dia:
                                  aux = (number_of_days + vac_days)/ 5
                               else:
                                  aux = 2
                         elif self.employee_id.tipo_semana == '03': # 4 días laborados x 3 de descanso
                            number_of_days -= 3
                            if self.employee_id.incapa_sept_dia:
                               aux = (number_of_days + inc_days + vac_days) / 4
                            else:
                               if self.employee_id.septimo_dia:
                                  aux = (number_of_days + vac_days)/ 4
                               else:
                                  aux = 3
                         else:
                            number_of_days -= 1
                            if self.employee_id.incapa_sept_dia:
                               if inc_days >= 6:
                                  aux = 0
                               else:
                                  aux = (number_of_days + vac_days) / 6
                            else:
                               if self.employee_id.septimo_dia:
                                  aux = (number_of_days + vac_days + inc_days)/ 6
                               else:
                                  aux = 1
                      work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','SEPT')])
                      attendances = {
                          'sequence': work_entry_type.sequence,
                          'work_entry_type_id': work_entry_type.id,
                          'number_of_days': aux, 
                          'number_of_hours': round(aux*8,2),
                      }
                      res.append(attendances)
                      if falta_days >= 6 or inc_days >= 6 or vac_days >= 6:
                         number_of_days = 0
                   else:
                      if falta_days >= 6 or inc_days >= 6 or vac_days >= 6:
                         number_of_days = 0
               #calculo para nóminas mensuales
               elif self.employee_id.periodicidad_pago == '05':
                  if self.employee_id.conteo_dias == '01':
                      total_days = work_data_days + leave_days
                      if total_days != 30:
                         if leave_days == 0 and not nvo_ingreso:
                            number_of_days = 30
                         elif nvo_ingreso:
                            number_of_days = work_data_days - leave_days
                         else:
                            number_of_days = 30 - leave_days
                      else:
                         number_of_days = 30
                  elif self.employee_id.conteo_dias == '03':
                      total_days = work_data_days + leave_days
                      if total_days != 30.42:
                         if leave_days == 0  and not nvo_ingreso:
                            number_of_days = 30.42
                         elif nvo_ingreso:
                            number_of_days = work_data_days * 30.42 / 30 - leave_days
                         else:
                            number_of_days = 30.42 - leave_days
                      else:
                         number_of_days = work_data_days * 30.42 / 30
                  else:
                      dias_periodo = (date_to - date_from).days + 1
                      total_days = work_data_days + leave_days
                      if total_days != dias_periodo:
                         if leave_days == 0  and not nvo_ingreso:
                            number_of_days = dias_periodo
                         elif nvo_ingreso:
                            number_of_days = work_data_days - leave_days
                         else:
                            number_of_days = dias_periodo - leave_days
                      else:
                         number_of_days = work_data_days
               else:
                  number_of_days = work_data_days
        else:
            if self.employee_id.work_entry_source != 'attendance':
               date_start = self.employee_id.contract_date_start
               if date_start:
                   d_from = fields.Date.from_string(date_from)
                   d_to = fields.Date.from_string(date_to)
               if date_start > self.date_from:
                   number_of_days = (d_to - date_start).days + 1 - leave_days
               else:
                   number_of_days = (d_to - d_from).days + 1 - leave_days
            else:
                number_of_days =  (self.date_to - self.date_from).days + 1 - leave_days

        #cambiar el que ya estaba esrito
        #if number_of_days != work_data_days:
        for line in res:
              work_entry_type = self.env['hr.work.entry.type'].browse(line['work_entry_type_id'])
              if work_entry_type.code == "WORK100":
                   line['number_of_days'] = number_of_days

        return res

    def _get_worked_day_lines(self, domain=None, check_out_of_contract=True):
        """
        :returns: a list of dict containing the worked days values that should be applied for the given payslip
        """
        res = []
        # fill only if the contract as a working schedule linked
        self.ensure_one()
        if self.country_code != 'MX':
            return super(HrPayslip,self)._get_worked_day_lines()
        contract = self.version_id
        if contract.resource_calendar_id:
            res = self._get_worked_day_lines_values(domain=domain)
            if not check_out_of_contract:
                return res

        horas_obj = self.env['horas.nomina']
        tipo_de_hora_mapping = {'1':'HEX1', '2':'HEX2', '3':'HEX3'}
        
        def is_number(s):
            try:
                return float(s)
            except ValueError:
                return 0

        # agregar prima vacacional, prima dominical y horas extras
        movimientos = True
        if movimientos:
            day_from = datetime.datetime.combine(fields.Date.from_string(self.date_from), datetime.time.min)
            day_to = datetime.datetime.combine(fields.Date.from_string(self.date_to), datetime.time.max)
            nb_of_days = (day_to - day_from).days + 1

            # compute Prima vacacional en fecha correcta
            if self.employee_id.tipo_prima_vacacional == '01':
                date_start = contract.date_start
                if date_start:
                    d_from = fields.Date.from_string(self.date_from)
                    d_to = fields.Date.from_string(self.date_to)
                
                    date_start = fields.Date.from_string(date_start)
                    if datetime.datetime.today().year > date_start.year:
                        if str(date_start.day) == '29' and str(date_start.month) == '2':
                            date_start -=  datetime.timedelta(days=1)
                        date_start = date_start.replace(d_to.year)

                        if d_from <= date_start <= d_to:
                            diff_date = day_to - datetime.datetime.combine(contract.date_start, datetime.time.max)
                            years = diff_date.days /365.0
                            antiguedad_anos = int(years)
                            tabla_antiguedades = contract.tablas_cfdi_id.tabla_antiguedades.filtered(lambda x: x.antiguedad <= antiguedad_anos)
                            tabla_antiguedades = tabla_antiguedades.sorted(lambda x:x.antiguedad, reverse=True)
                            vacaciones = tabla_antiguedades and tabla_antiguedades[0].vacaciones or 0
                            prima_vac = tabla_antiguedades and tabla_antiguedades[0].prima_vac or 0
                            work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','PVC')])
                            attendances = {
                                 'sequence': work_entry_type.sequence,
                                 'work_entry_type_id': work_entry_type.id,
                                 'number_of_days': vacaciones * prima_vac / 100.0,
                                 'number_of_hours': vacaciones * prima_vac / 100.0 * 8,
                            }
                            res.append(attendances)

            # compute Prima vacacional
            if self.employee_id.tipo_prima_vacacional == '03':
                date_start = contract.date_start
                if date_start:
                    d_from = fields.Date.from_string(self.date_from)
                    d_to = fields.Date.from_string(self.date_to)

                    date_start = fields.Date.from_string(date_start)
                    if datetime.datetime.today().year > date_start.year and d_from.day > 15:
                        if str(date_start.day) == '29' and str(date_start.month) == '2':
                            date_start -=  datetime.timedelta(days=1)
                        date_start = date_start.replace(d_to.year)
                        d_from = d_from.replace(day=1)

                        if d_from <= date_start <= d_to:
                            diff_date = day_to - datetime.datetime.combine(contract.date_start, datetime.time.max)
                            years = diff_date.days /365.0
                            antiguedad_anos = int(years)
                            tabla_antiguedades = contract.tablas_cfdi_id.tabla_antiguedades.filtered(lambda x: x.antiguedad <= antiguedad_anos)
                            tabla_antiguedades = tabla_antiguedades.sorted(lambda x:x.antiguedad, reverse=True)
                            vacaciones = tabla_antiguedades and tabla_antiguedades[0].vacaciones or 0
                            prima_vac = tabla_antiguedades and tabla_antiguedades[0].prima_vac or 0
                            work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','PVC')])
                            attendances = {
                                 'sequence': work_entry_type.sequence,
                                 'work_entry_type_id': work_entry_type.id,
                                 'number_of_days': vacaciones * prima_vac / 100.0,
                                 'number_of_hours': vacaciones * prima_vac / 100.0 * 8,
                            }
                            res.append(attendances)

            # compute Prima dominical
            if self.employee_id.prima_dominical:
                domingos = 0
                d_from = fields.Date.from_string(self.date_from)
                d_to = fields.Date.from_string(self.date_to)
                for i in range((d_to - d_from).days + 1):
                    if (d_from + datetime.timedelta(days=i+1)).weekday() == 0:
                        domingos = domingos + 1

                work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=','PDM')])
                attendances = {
                            'sequence': work_entry_type.sequence,
                            'work_entry_type_id': work_entry_type.id,
                            'number_of_days': domingos,
                            'number_of_hours': domingos * 8,
                     }
                res.append(attendances)

            #Compute horas extas
            horas = horas_obj.search([('employee_id','=',self.employee_id.id),('fecha','>=',self.date_from), ('fecha', '<=', self.date_to),('state','=','done')])
            horas_by_tipo_de_horaextra = defaultdict(list)
            for h in horas:
                horas_by_tipo_de_horaextra[h.tipo_de_hora].append(h.horas)

            for tipo_de_hora, horas_set in horas_by_tipo_de_horaextra.items():
                work_code = tipo_de_hora_mapping.get(tipo_de_hora,'')
                number_of_days = len(horas_set)
                number_of_hours = sum(is_number(hs) for hs in horas_set)

                work_entry_type = self.env['hr.work.entry.type'].sudo().search([('code','=',work_code)])
                attendances = {
                    'sequence': work_entry_type.sequence,
                    'work_entry_type_id': work_entry_type.id,
                    'number_of_days': number_of_days, 
                    'number_of_hours': number_of_hours,
                }
                res.append(attendances)

        return res

   # @api.onchange('contract_id')
    def _get_periodicidad(self):
        for invoice in self:
          invoice.periodicidad_pago = invoice.employee_id.periodicidad_pago

    def set_fecha_pago(self, payroll_name):
            values = {
                'payslip_run_id': payroll_name
                }
            self.update(values)

    @api.onchange('date_to')
    def _get_fecha_pago(self):
        if self.date_to:
            values = {
                'fecha_pago': self.date_to
                }
            self.update(values)

    @api.onchange('date_to')
    def _get_dias_periodo(self):
        self.dias_periodo = 0
        if self.mes:
            line = self.employee_id.env['tablas.periodo.mensual'].search([('form_id','=',self.employee_id.tablas_cfdi_id.id),('mes','=',self.mes)],limit=1)
            if line:
                self.dias_periodo = line.no_dias
            else:
                raise UserError(_('No están configurados correctamente los periodos en las tablas CFDI'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
           if not vals.get('fecha_pago') and vals.get('date_to'):
               vals.update({'fecha_pago': vals.get('date_to')})
            
        res = super(HrPayslip, self).create(vals_list)
        return res

    @api.depends('name')
    def _get_number_folio(self):
        for payslip in self:
           if payslip.name:
               payslip.number_folio = payslip.name.replace('SLIP','').replace('NOM','').replace('/','')
           else:
               raise UserError(_('La nómina no tiene un número asignado.'))

#    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        default = dict(default or {})
        if self.estado_factura == 'factura_correcta' or self.estado_factura == 'factura_cancelada':
            default['estado_factura'] = 'factura_no_generada'
            default['folio_fiscal'] = ''
            default['fecha_factura'] = None
            default['nomina_cfdi'] = False
        return super(HrPayslip, self).copy(default=default)

    def _get_fondo_ahorro(self):
        total = 0
        if self.employee_id and self.employee_id.tablas_cfdi_id:
            abono = 0
            retiro = 0
            domain=[('state','=', 'done')]
            domain.append(('employee_id','=',self.employee_id.id))
            if self.employee_id.tablas_cfdi_id.caja_ahorro_abono:
                        rules = self.env['hr.salary.rule'].search([('code', '=', self.employee_id.tablas_cfdi_id.caja_ahorro_abono.code)])
                        payslips = self.env['hr.payslip'].search(domain)
                        payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
                        employees = {}
                        for line in payslip_lines:
                           if line.slip_id.employee_id not in employees:
                              employees[line.slip_id.employee_id] = {line.slip_id: []}
                           if line.slip_id not in employees[line.slip_id.employee_id]:
                              employees[line.slip_id.employee_id].update({line.slip_id: []})
                           employees[line.slip_id.employee_id][line.slip_id].append(line)
                        for employee, payslips in employees.items():
                            for payslip2,lines in payslips.items():
                               for line in lines:
                                  abono += line.total
            if self.employee_id.tablas_cfdi_id.caja_ahorro_retiro:
                        rules = self.env['hr.salary.rule'].search([('code', '=', self.employee_id.tablas_cfdi_id.caja_ahorro_retiro.code)])
                        payslips = self.env['hr.payslip'].search(domain)
                        payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
                        employees = {}
                        for line in payslip_lines:
                           if line.slip_id.employee_id not in employees:
                              employees[line.slip_id.employee_id] = {line.slip_id: []}
                           if line.slip_id not in employees[line.slip_id.employee_id]:
                              employees[line.slip_id.employee_id].update({line.slip_id: []})
                           employees[line.slip_id.employee_id][line.slip_id].append(line)
                        for employee, payslips in employees.items():
                            for payslip2,lines in payslips.items():
                               for line in lines:
                                  retiro += line.total
            self.acum_fondo_ahorro = abono - retiro

    def acumulado_mes(self, codigo):
        total = 0
        if self.employee_id and self.employee_id.tablas_cfdi_id:
            mes_actual = self.employee_id.tablas_cfdi_id.tabla_mensual.search([('mes', '=', self.mes), ('form_id', '=', self.employee_id.tablas_cfdi_id.id)],limit =1)
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','in', ['paid', 'done'])]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            if not self.employee_id.calc_isr_extra:
               domain.append(('tipo_nomina','=','O'))
            rules = self.env['hr.salary.rule'].search([('code', '=', codigo)])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        return total

    def mensual(self, employee_id, contract_id, mes, codigo):
        total = 0
        if employee_id and employee_id.tablas_cfdi_id:
            mes_actual = employee_id.tablas_cfdi_id.tabla_mensual.search([('mes', '=', mes), ('form_id', '=', employee_id.tablas_cfdi_id.id)],limit =1)
            date_start = mes_actual.dia_inicio # self.date_from
            date_end = mes_actual.dia_fin #self.date_to
            domain=[('state','in', ['paid', 'done'])]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',employee_id.id))
            if not employee_id.calc_isr_extra:
               domain.append(('tipo_nomina','=','O'))
            rules = self.env['hr.salary.rule'].search([('code', '=', codigo)])
            payslips = self.env['hr.payslip'].search(domain)
            payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
            employees = {}
            for line in payslip_lines:
                if line.slip_id.employee_id not in employees:
                    employees[line.slip_id.employee_id] = {line.slip_id: []}
                if line.slip_id not in employees[line.slip_id.employee_id]:
                    employees[line.slip_id.employee_id].update({line.slip_id: []})
                employees[line.slip_id.employee_id][line.slip_id].append(line)

            for employee, payslips in employees.items():
                for payslip,lines in payslips.items():
                    for line in lines:
                        total += line.total
        return total

    def anual(self, employee_id, contract_id, date_from, codigo):
        total = 0
        if employee_id and employee_id.tablas_cfdi_id:
            date_start = date(fields.Date.from_string(date_from).year, 1, 1)
            date_end = date(fields.Date.from_string(date_from).year, 12, 31)
            domain=[('state','in', ['paid', 'done'])]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',employee_id.id))
            if codigo != 'ISR2':
               rules = self.env['hr.salary.rule'].search([('code', '=', codigo)])
               payslips = self.env['hr.payslip'].search(domain)
               payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
               employees = {}
               for line in payslip_lines:
                   if line.slip_id.employee_id not in employees:
                       employees[line.slip_id.employee_id] = {line.slip_id: []}
                   if line.slip_id not in employees[line.slip_id.employee_id]:
                       employees[line.slip_id.employee_id].update({line.slip_id: []})
                   employees[line.slip_id.employee_id][line.slip_id].append(line)

               for employee, payslips in employees.items():
                   for payslip,lines in payslips.items():
                       for line in lines:
                           total += line.total
            else:
               payslips = self.env['hr.payslip'].search(domain)
               for slip in payslips:
                   isr = 0
                   isr_antes = 0
                   for line in slip.line_ids:
                      if line.code == 'ISR2':
                         isr = line.total
                      elif line.code == 'ISR':
                         isr_antes = line.total
                   if isr > isr_antes:
                      total += isr
                   else:
                      total += isr_antes
        return total

    def acumulado_anual(self, codigo):
        total = 0
        if self.employee_id and self.employee_id.tablas_cfdi_id:
            date_start = date(fields.Date.from_string(self.date_from).year, 1, 1)
            date_end = date(fields.Date.from_string(self.date_from).year, 12, 31)
            domain=[('state','in', ['paid', 'done'])]
            if date_start:
                domain.append(('date_from','>=',date_start))
            if date_end:
                domain.append(('date_to','<=',date_end))
            domain.append(('employee_id','=',self.employee_id.id))
            if codigo != 'ISR2':
               rules = self.env['hr.salary.rule'].search([('code', '=', codigo)])
               payslips = self.env['hr.payslip'].search(domain)
               payslip_lines = payslips.mapped('line_ids').filtered(lambda x: x.salary_rule_id.id in rules.ids)
               employees = {}
               for line in payslip_lines:
                   if line.slip_id.employee_id not in employees:
                       employees[line.slip_id.employee_id] = {line.slip_id: []}
                   if line.slip_id not in employees[line.slip_id.employee_id]:
                       employees[line.slip_id.employee_id].update({line.slip_id: []})
                   employees[line.slip_id.employee_id][line.slip_id].append(line)

               for employee, payslips in employees.items():
                   for payslip,lines in payslips.items():
                       for line in lines:
                           total += line.total
            else:
               payslips = self.env['hr.payslip'].search(domain)
               for slip in payslips:
                   isr = 0
                   isr_antes = 0
                   for line in slip.line_ids:
                      if line.code == 'ISR2':
                         isr = line.total
                      elif line.code == 'ISR':
                         isr_antes = line.total
                   if isr > isr_antes:
                      total += isr
                   else:
                      total += isr_antes
        return total

    def _get_acumulados_mensual(self):
         if self.state != 'done':
             self.acum_sueldo = self.acumulado_mes('P001')
             self.acum_per_totales = self.acumulado_mes('TPER')
             self.acum_subsidio_aplicado = self.acumulado_mes('SUB')
             self.acum_isr_antes_subem = self.acumulado_mes('ISR')
             self.acum_per_grav = self.acumulado_mes('TPERG')
             self.acum_isr = self.acumulado_mes('ISR2')

    def _get_acumulados_anual(self):
         if self.state != 'done' and self.isr_anual:
             self.acum_subsidio_aplicado_anual = self.acumulado_anual('SUB')
            # self.acum_isr_antes_subem_anual = self.acumulado_anual('ISR')
             self.acum_per_grav_anual = self.acumulado_anual('TPERG')
             self.acum_isr_anual = self.acumulado_anual('ISR2')
             self.acum_dev_isr = self.acumulado_anual('O007')
             self.acum_dev_subem = self.acumulado_anual('D061')
             self.acum_dev_subem_entregado = self.acumulado_anual('D062')
             self.acum_isr_ajuste = self.acumulado_anual('D060')

    def _get_acumulado_prima_vac(self):
         self.acum_prima_vac_exento = self.acumulado_anual('PE010')

    def _validate_slip_fields(self):
         if not self.version_id:
             raise UserError(_('El empleado %s no tiene contrato asignado.') % (self.employee_id.name))
         if not self.version_id.tablas_cfdi_id:
             raise UserError(_('El empleado %s no tiene tablas CFDI asignado en el contrato.') % (self.employee_id.name))
#         if self.dias_pagar <= 0:
#             raise UserError(_('El empleado %s no tiene asignados días a pagar.') % (self.employee_id.name))


    @api.model
    def _get_nomina_template(self):
        return 'nomina_cfdi_ee.cfdi_nomina'

    def send_nomina(self):
        self.ensure_one()
        template = self.env.ref('nomina_cfdi_ee.email_template_payroll', False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
            
        ctx = dict()
        ctx.update({
            'default_model': 'hr.payslip',
            'default_res_ids': [self.id],
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

    def action_payslip_done(self):
        res = super(HrPayslip,self).action_payslip_done()
        for rec in self:
            if rec.country_code != 'MX':
               return super(HrPayslip,rec).action_payslip_done()
            rec._get_fondo_ahorro()
        return res

    def compute_sheet(self):
        for invoice in self:
            if invoice.country_code != 'MX':
               return super(HrPayslip,invoice).compute_sheet()
            invoice._validate_slip_fields()
            invoice._get_acumulados_mensual()
            invoice._get_acumulados_anual()
            invoice._get_acumulado_prima_vac()
#            invoice.compania_padre = invoice.company_id.sudo().parent_ids[::-1].filtered('partner_id.vat')[:1] or invoice.company_id
#            if not invoice.compania_padre:
#                invoice.compania_padre = invoice.company_id.id

        res = super(HrPayslip, self).compute_sheet()
        for rec in self:
            rec.calculo_imss()
            rec.total_nom = rec.get_amount_from_rule_code('NET')
            #calculo de especie
            total = 0
            #_logger.info('monto especie')
            for line in rec.line_ids:
                #_logger.info('codigo %s monto %s', line.code, line.total)
                if line.salary_rule_id.forma_pago == '002':
                   #_logger.info('entro codigo %s monto %s', line.code, line.total)
                   total += line.total
            #_logger.info('total especie %s', total)
            lines = []
            for line in rec.line_ids:
                if line.code == 'EFECT':
                   #_logger.info('codigo %s monto %s', line.code, line.total)
                   line.update({'total': line.total - total, 'amount': line.total - total})
#                   line.refresh()
#            rec.refresh()
            #quitar prestamos cuando nomina en cero
            if rec.total_nom <= 0 and rec.aplicar_descuentos:
               rec.aplicar_descuentos = False
        return res

    @api.model
    def calculo_imss(self):
        #cuota del IMSS parte del Empleado
        dias_laborados = 0
        dias_completos = 0
        dias_falta = 0
        dias_trabajo = 0

        dias_completos = self.imss_dias
        dias_laborados =  dias_completos
        dias_falta =  dias_completos

        dias_registrados = self.env['hr.payslip.worked_days'].search([('payslip_id','=',self.id)])
        if dias_registrados:
            for dias in dias_registrados:
                if dias.code == 'FI' or dias.code == 'FJS':
                    dias_laborados = dias_laborados - dias.number_of_days
                    dias_falta = dias_falta - dias.number_of_days
                if dias.code == 'INC_MAT' or dias.code == 'INC_EG' or dias.code == 'INC_RT':
                    dias_laborados = dias_laborados - dias.number_of_days
                    dias_completos = dias_completos - dias.number_of_days
                if dias.code == 'WORK100' or dias.code == 'FJC' or dias.code == 'SEPT' or dias.code == 'VAC':
                    dias_trabajo = dias_trabajo + dias.number_of_days
        if dias_trabajo == 0:
            dias_laborados = 0
            dias_completos = 0

        #salario_cotizado = self.contract_id.sueldo_base_cotizacion
        base_calculo = 0
        base_execente = 0
        if self.employee_id.sueldo_base_cotizacion < 25 * self.employee_id.tablas_cfdi_id.uma:
            base_calculo = self.employee_id.sueldo_base_cotizacion
        else:
            base_calculo = 25 * self.employee_id.tablas_cfdi_id.uma

        if base_calculo > 3 * self.employee_id.tablas_cfdi_id.uma:
            base_execente = base_calculo - 3 * self.employee_id.tablas_cfdi_id.uma

        if self.employee_id.regimen == '02' or self.employee_id.regimen == '13':
            self.emp_exedente_smg = round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_excedente_e/100 * base_execente,2)
            self.emp_prest_dinero = round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_prestaciones_e/100 * base_calculo,2)
            self.emp_esp_pens = round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_gastos_med_e/100 * base_calculo,2)
            self.emp_invalidez_vida = round(dias_laborados * self.employee_id.tablas_cfdi_id.inv_vida_e/100 * base_calculo,2)
            self.emp_cesantia_vejez = round(dias_laborados * self.employee_id.tablas_cfdi_id.cesantia_vejez_e/100 * base_calculo,2)
            self.emp_total = self.emp_exedente_smg + self.emp_prest_dinero + self.emp_esp_pens + self.emp_invalidez_vida + self.emp_cesantia_vejez
            
            #imss patronal
            factor_riesgo = 0
            if self.employee_id.riesgo_puesto == '1':
                factor_riesgo = self.employee_id.tablas_cfdi_id.rt_clase1
            elif self.employee_id.riesgo_puesto == '2':
                factor_riesgo = self.employee_id.tablas_cfdi_id.rt_clase2
            elif self.employee_id.riesgo_puesto == '3':
                factor_riesgo = self.employee_id.tablas_cfdi_id.rt_clase3
            elif self.employee_id.riesgo_puesto == '4':
                factor_riesgo = self.employee_id.tablas_cfdi_id.rt_clase4
            elif self.employee_id.riesgo_puesto == '5':
                factor_riesgo = self.employee_id.tablas_cfdi_id.rt_clase5

            tabla_cesantia = self.env['tablas.cesantia.line'].search([('form_id','=', self.employee_id.tablas_cfdi_id.id), 
                                                                      ('lim_inf','<=',self.employee_id.sueldo_base_cotizacion)],
                                                                      #('lim_sup','>=',self.employee_id.sueldo_base_cotizacion)],
                                                                       order='lim_inf desc',limit=1)
            if not tabla_cesantia:
                cesantia_vejez_p = self.employee_id.tablas_cfdi_id.cesantia_vejez_p
            else:
                cesantia_vejez_p = tabla_cesantia.cuota

            #_logger.info('cesantia: %s', cesantia_vejez_p)

            self.pat_cuota_fija_pat = round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_cuota_fija/100 * self.employee_id.tablas_cfdi_id.uma,2)
            self.pat_exedente_smg =round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_excedente_p/100 * base_execente,2)
            self.pat_prest_dinero = round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_prestaciones_p/100 * base_calculo,2)
            self.pat_esp_pens = round(dias_completos * self.employee_id.tablas_cfdi_id.enf_mat_gastos_med_p/100 * base_calculo,2)
            self.pat_riesgo_trabajo = round(dias_laborados * factor_riesgo/100 * base_calculo,2) # falta
            self.pat_invalidez_vida = round(dias_laborados * self.employee_id.tablas_cfdi_id.inv_vida_p/100 * base_calculo,2)
            self.pat_guarderias = round(dias_laborados * self.employee_id.tablas_cfdi_id.guarderia_p/100 * base_calculo,2)
            self.pat_retiro = round(dias_falta * self.employee_id.tablas_cfdi_id.retiro_p/100 * base_calculo,2)
            self.pat_cesantia_vejez = round(dias_laborados * cesantia_vejez_p/100 * base_calculo,2)
            self.pat_infonavit = round(dias_falta * self.employee_id.tablas_cfdi_id.apotacion_infonavit/100 * base_calculo,2)
            self.pat_total = self.pat_cuota_fija_pat + self.pat_exedente_smg + self.pat_prest_dinero + self.pat_esp_pens + self.pat_riesgo_trabajo + self.pat_invalidez_vida + self.pat_guarderias + self.pat_retiro + self.pat_cesantia_vejez + self.pat_infonavit
            if self.employee_id.sueldo_diario <= self.employee_id.tablas_cfdi_id.salario_minimo:
               self.pat_exedente_smg += self.emp_exedente_smg
               self.pat_prest_dinero += self.emp_prest_dinero
               self.pat_esp_pens += self.emp_esp_pens
               self.pat_invalidez_vida += self.emp_invalidez_vida
               self.pat_cesantia_vejez += self.emp_cesantia_vejez
               self.pat_total += self.emp_exedente_smg + self.emp_prest_dinero + self.emp_esp_pens + self.emp_invalidez_vida + self.emp_cesantia_vejez
               self.emp_exedente_smg = 0
               self.emp_prest_dinero = 0
               self.emp_esp_pens = 0
               self.emp_invalidez_vida = 0
               self.emp_cesantia_vejez = 0
               self.emp_total = 0
        else:
            #imss empleado
            self.emp_exedente_smg = 0
            self.emp_prest_dinero = 0
            self.emp_esp_pens = 0
            self.emp_invalidez_vida = 0
            self.emp_cesantia_vejez = 0
            self.emp_total = 0
            
            #imss patronal
            self.pat_cuota_fija_pat = 0
            self.pat_exedente_smg =0
            self.pat_prest_dinero = 0
            self.pat_esp_pens = 0
            self.pat_riesgo_trabajo = 0
            self.pat_invalidez_vida = 0
            self.pat_guarderias = 0
            self.pat_retiro = 0
            self.pat_cesantia_vejez = 0
            self.pat_infonavit = 0
            self.pat_total = 0

    def _get_cumpleanos(self):
        if self.employee_id.birthday:
          date_cumple = fields.Date.from_string(self.employee_id.birthday)
          if str(date_cumple.day) == '29' and str(date_cumple.month) == '2':
               date_cumple -=  datetime.timedelta(days=1)
          date_cumple = date_cumple.replace(self.date_to.year)
          d_from = fields.Date.from_string(self.date_from)
          #d_from = d_from.replace(date_cumple.year)
          d_to = fields.Date.from_string(self.date_to)
          #d_to = d_to.replace(date_cumple.year)
          if d_from <= date_cumple <= d_to:
              self.cumpleanos = True
          else:
              self.cumpleanos = False
        else:
          self.cumpleanos = False

    def set_decimals(self, amount, precision):
        if amount is None or amount is False:
            return None
        return '%.*f' % (precision, amount)

    def read_xml_report_values(self):
        for payslip in self:
            domain = [('res_id', '=', payslip.id),
                      ('res_model', '=', payslip._name),
                      ('name', '=', payslip.number.replace('/', '_') + '.xml')]
            xml_file = payslip.env['ir.attachment'].search(domain, limit=1)
            if not xml_file:
                return round(payslip.employee_id.sueldo_diario_integrado,2)
            else: 
                attch_file = base64.b64decode(xml_file.datas)
                xml_data = etree.fromstring(attch_file)
                NSMAP = {
                     'xsi':'http://www.w3.org/2001/XMLSchema-instance',
                     'cfdi':'http://www.sat.gob.mx/cfd/4', 
                     'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
                     'nomina12': 'http://www.sat.gob.mx/nomina12',
                }
                Complemento = xml_data.findall('cfdi:Complemento', NSMAP)
                for complementos in Complemento:
                      nominas = complementos.find('nomina12:Nomina', NSMAP)
                      nomina = nominas.find('nomina12:Receptor', NSMAP)
                      if 'SalarioDiarioIntegrado' in nomina:
                          salario_amount = nomina.attrib['SalarioDiarioIntegrado']
                      else:
                          salario_amount = round(payslip.employee_id.sueldo_diario_integrado,2)
            return salario_amount

class HrPayslipMail(models.Model):
    _name = "hr.payslip.mail"
    _inherit = ['mail.thread']
    _description = "Nomina Mail"

    payslip_id = fields.Many2one('hr.payslip', string='Nomina')
    name = fields.Char(related='payslip_id.name')
    employee_id = fields.Many2one(related='payslip_id.employee_id')
    company_id = fields.Many2one(related='payslip_id.company_id')


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def _compute_attachment_ids(self):
        res = super(MailComposeMessage, self)._compute_attachment_ids()
        for rec in self:
            if rec.model == 'hr.payslip':
                attachment_ids=[]
                template_id = rec.env.ref('nomina_cfdi_ee.email_template_payroll')
                if rec.template_id.id == template_id.id:
                    res_ids = ast.literal_eval(rec.res_ids)
                    for res_id in res_ids:
                        slip = rec.env[rec.model].browse(res_id)
                        domain = [
                            ('res_id', '=', slip.id),
                            ('res_model', '=', slip._name),
                            ('name', '=', slip.number.replace('/', '_') + '.xml')]
                        xml_file = rec.env['ir.attachment'].search(domain, limit=1)
                        if xml_file:
                            attachment_ids.extend(rec.attachment_ids.ids)
                            attachment_ids.append(xml_file.id)
                    if attachment_ids:
                        rec.attachment_ids = [(6, 0, attachment_ids)]
        return res
