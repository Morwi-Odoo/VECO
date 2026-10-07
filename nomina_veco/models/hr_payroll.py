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

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

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
        if self.employee_id.periodicidad_pago == '02':
            if self.employee_id.tipo_semana == '02':
                dias_pagar = 7.0192
                factor = 7.0192/6.0
            elif self.employee_id.tipo_semana == '03':
                factor = 7.0/4.0
            else:
                dias_pagar = 15.2083
                factor = 1.16
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
                   if total_days != 7.0192 or leave_days != 0:
                      if leave_days == 0 and not nvo_ingreso:
                         number_of_days = 7.0192
                      elif nvo_ingreso:
                         number_of_days = work_data_days * 7.0192 / 7 - leave_days
                      else:
                         number_of_days = 7.0192 - leave_days
                   else:
                      number_of_days = work_data_days * 7.0192 / 7
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
