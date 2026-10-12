# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from datetime import datetime, date, time
from dateutil.relativedelta import relativedelta
from calendar import monthrange
import logging
_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError
import io
import base64
import pytz

class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def generate_payslips(self, version_ids=None, employee_ids=None):
        # EXTENDS 'hr_payroll' - ports the old nomina_cfdi_ee hr.payslip.employees wizard
        # (removed in 19.0, replaced by this method) so that the batch's own CFDI fields
        # (dias_pagar, imss_mes, periodicidad_pago, tipo_nomina, ...) seed every payslip
        # it generates. Can't call super() and patch afterwards: compute_sheet() runs
        # inside the native method, so these fields must already be set before that call.
        self.ensure_one()

        if employee_ids and not version_ids:
            version_ids = self._get_valid_version_ids(employee_ids=employee_ids)

        if not version_ids:
            raise UserError(_("You must select employee(s) version(s) to generate payslip(s)."))

        valid_versions = self.env["hr.version"].browse(version_ids)

        Payslip = self.env['hr.payslip']

        if self.estructura:
            valid_versions = valid_versions.filtered(lambda c: c.structure_type_id.id == self.estructura.type_id.id)
        valid_versions.generate_work_entries(self.date_start, self.date_end)

        all_work_entries = dict(self.env['hr.work.entry']._read_group(
            domain=[
                ('employee_id', 'in', valid_versions.employee_id.ids),
                ('date', '<=', self.date_end),
                ('date', '>=', self.date_start),
            ],
            groupby=['version_id'],
            aggregates=['id:recordset'],
        ))

        utc = pytz.utc
        for tz, slips_per_tz in self.slip_ids.grouped(lambda s: s.version_id.tz).items():
            slip_tz = pytz.timezone(tz or utc)
            for slip in slips_per_tz:
                date_from = slip_tz.localize(datetime.combine(slip.date_from, time.min)).astimezone(utc).replace(tzinfo=None)
                date_to = slip_tz.localize(datetime.combine(slip.date_to, time.max)).astimezone(utc).replace(tzinfo=None)
                if version_work_entries := all_work_entries.get(slip.version_id):
                    version_work_entries.filtered_domain([
                        ('date', '<=', date_to),
                        ('date', '>=', date_from),
                    ])
                    version_work_entries._check_undefined_slots(slip.date_from, slip.date_to)

        for work_entries in all_work_entries.values():
            work_entries = work_entries.filtered(lambda we: we.state != 'validated')
            if work_entries._check_if_error():
                work_entries = work_entries.filtered(lambda we: we.state == 'conflict')
                conflicts = work_entries._to_intervals()
                time_intervals_str = "".join(
                    f"\n - {start} -> {end} ({entry.employee_id.name})" for start, end, entry in conflicts._items)
                raise UserError(self.env._("Some work entries could not be validated. Time intervals to look for:%s", time_intervals_str))

        default_values = Payslip.default_get(Payslip.fields_get())
        payslips_vals = []
        for version in valid_versions[::-1]:
            values = default_values | {
                'name': self.env._('New Payslip'),
                'employee_id': version.employee_id.id,
                'payslip_run_id': self.id,
                'date_from': self.date_start,
                'date_to': self.date_end,
                'version_id': version.id,
                'company_id': self.company_id.id,
                'struct_id': self.estructura.id or version.structure_type_id.default_struct_id.id,
                'dias_pagar': self.dias_pagar,
                'imss_mes': self.imss_mes,
                'imss_dias': self.imss_dias,
                'ultima_nomina': self.ultima_nomina,
                'mes': self.mes,
                'isr_ajustar': self.isr_ajustar,
                'isr_anual': self.isr_anual,
                'concepto_periodico': self.concepto_periodico,
                'tipo_nomina': self.tipo_nomina,
                'fecha_pago': self.fecha_pago,
            }
            payslips_vals.append(values)
        self.slip_ids |= Payslip.with_context(tracking_disable=True).create(payslips_vals)
        self.slip_ids._compute_name()
        self.slip_ids.compute_sheet()
        self.state = '01_ready'

        return 1


    def action_confirmar_nomina(self):
        for rec in self:
            slip_ids = rec.slip_ids.filtered(lambda r: r.state == 'draft')
            for slip_id in slip_ids:
                slip_id.action_payslip_done()

    def action_cancelar_nomina(self):
        for rec in self:
            slip_ids = rec.slip_ids.filtered(lambda r: r.state == 'validated')
            for slip_id in slip_ids:
                slip_id.action_payslip_cancel()

    tipo_configuracion = fields.Many2one('configuracion.nomina', string='Configuración')
    all_payslip_generated = fields.Boolean("Payslip Generated",compute='_compute_payslip_cgdi_generated')
    all_payslip_generated_draft = fields.Boolean("Payslip Generated draft",compute='_compute_payslip_cgdi_generated_draft')
    tipo_nomina = fields.Selection(
        selection=[('O', 'Nómina ordinaria'), ('E', 'Nómina extraordinaria'),], string=_('Tipo de nómina'), required=True, default='O')
    estructura = fields.Many2one('hr.payroll.structure', string='Estructura')
    tabla_otras_entradas = fields.One2many('otras.entradas', 'form_id')
    dias_pagar = fields.Float(string='Dias a pagar', store=True)
    imss_dias = fields.Float(string='Dias a cotizar en la nómina', store=True)
    imss_mes = fields.Float(string='Dias en el mes', store=True)
    ultima_nomina = fields.Boolean(string='Última nómina del mes')
    nominas_mes = fields.Integer('Nóminas a pagar en el mes')
    concepto_periodico = fields.Boolean('Conceptos periódicos', default = True)
    isr_ajustar = fields.Boolean(string='Ajustar ISR (mensual)')
    #isr_devolver = fields.Boolean(string='Devolver ISR')
    periodicidad_pago = fields.Selection(
        selection=[('01', 'Diario'), 
                   ('02', 'Semanal'), 
                   ('03', 'Catorcenal'),
                   ('04', 'Quincenal'), 
                   ('05', 'Mensual'),
                   ('06', 'Bimensual'), 
                   ('07', 'Unidad obra'),
                   ('08', 'Comisión'), 
                   ('09', 'Precio alzado'), 
                   ('10', 'Pago por consignación'), 
                   ('99', 'Otra periodicidad'),],
        string=_('Frecuencia de pago'), required=True
    )
    fecha_pago = fields.Date(string=_('Fecha de pago'), required=True)
    isr_anual = fields.Boolean(string='ISR anual')
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
        string=_('Mes / Periodo'),)

    @api.onchange('tipo_configuracion')
    def _set_periodicidad(self):
        if self.tipo_configuracion:
            if self.tipo_configuracion.fijo_imss:
                values = {
                   'periodicidad_pago': self.tipo_configuracion.periodicidad_pago,
                   'isr_ajustar': self.tipo_configuracion.isr_ajustar,
                   #'isr_devolver': self.tipo_configuracion.isr_devolver,
                   'imss_mes': self.tipo_configuracion.imss_mes,
                   'imss_dias': self.tipo_configuracion.imss_dias,
                   }
            else:
                values = {
                   'periodicidad_pago': self.tipo_configuracion.periodicidad_pago,
                   'isr_ajustar': self.tipo_configuracion.isr_ajustar,
                   #'isr_devolver': self.tipo_configuracion.isr_devolver,
               }
            self.update(values)


    @api.onchange('periodicidad_pago', 'tipo_configuracion')
    def _dias_pagar(self):
        if self.periodicidad_pago:
            if self.periodicidad_pago == '01':
                self.dias_pagar = 1
            elif self.periodicidad_pago == '02':
                self.dias_pagar = 7
            elif self.periodicidad_pago == '03':
                self.dias_pagar = 14
            elif self.periodicidad_pago == '04':
                if self.tipo_configuracion.tipo_pago == '01':
                    self.dias_pagar = 15
                    self.imss_dias = self.imss_mes / 2
                elif self.tipo_configuracion.tipo_pago == '02':
                    delta = self.date_end - self.date_start
                    self.dias_pagar = delta.days + 1
                    self.imss_dias = delta.days + 1
                else:
                    self.dias_pagar = 15.21
                    self.imss_dias = 15.21
            elif self.periodicidad_pago == '05':
                if self.tipo_configuracion.tipo_pago == '01':
                    self.dias_pagar = 30
                elif self.tipo_configuracion.tipo_pago == '02':
                    delta = self.date_end - self.date_start
                    self.dias_pagar = delta.days + 1
                else:
                    self.dias_pagar = 30.42
            else:
                delta = self.date_end - self.date_start
                self.dias_pagar = delta.days + 1

    @api.onchange('periodicidad_pago', 'date_end')
    def _compute_imss_mes(self):
        for batch in self:
            if batch.date_end:
                if self.tipo_configuracion:
                    if not self.tipo_configuracion.fijo_imss:
                        date_end = batch.date_end
                        batch.imss_mes = monthrange(date_end.year,date_end.month)[1]
                    else:
                        batch.imss_mes = self.tipo_configuracion.imss_mes
                else:
                    date_end = batch.date_end
                    batch.imss_mes = monthrange(date_end.year,date_end.month)[1]

    @api.onchange('nominas_mes')
    def _get_imss_dias(self):
        if self.nominas_mes and self.periodicidad_pago != '04':
            if self.tipo_configuracion:
                if not self.tipo_configuracion.fijo_imss:
                    values = {
                       'imss_dias': self.imss_mes / self.nominas_mes
                   }
                    self.update(values)
                else:
                    values = {
                       'imss_dias': self.tipo_configuracion.imss_dias
                   }
                    self.update(values)
            else:
                values = {
                     'imss_dias': self.imss_mes / self.nominas_mes
                 }
                self.update(values)

    @api.onchange('periodicidad_pago')
    def _update_nominas_mes(self):
        for batch in self:
            if self.periodicidad_pago:
                if self.periodicidad_pago == '02':
                    batch.nominas_mes = 4
                if self.periodicidad_pago == '04':
                    batch.nominas_mes = 2

    def recalcular_nomina(self):
        self.ensure_one()
        view = self.env.ref('nomina_cfdi_ee.recalcular_nomina_wizard')
        ctx = self.env.context.copy()
        ctx.update({'default_payslip_batch_id': self.id})
        return {
            'name': 'Recalcular De Nomina',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'recalcular.de.nomina',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': ctx,
        }

    def recalcular_nomina_wizard(self):
        self.ensure_one()
        payslip_obj = self.env['hr.payslip']
        start_range = self._context.get('start_range')
        end_range = self._context.get('end_range')
        for payslip_id in self.slip_ids.ids:
            payslip = payslip_obj.browse(payslip_id)
            if start_range and end_range:
                emp_no = int(payslip.employee_id.no_empleado)
                if emp_no >= start_range and emp_no <= end_range:
                    if payslip.state == 'draft':
                        payslip.compute_sheet()
            else:
                if payslip.state == 'draft':
                    payslip.compute_sheet()
        return True
     
    @api.depends('slip_ids.state','slip_ids.nomina_cfdi')
    def _compute_payslip_cgdi_generated(self):
        cfdi_generated = True
        for payslip in self.slip_ids:
            if payslip.state == 'draft' or not payslip.nomina_cfdi:
                cfdi_generated=False
                break
        self.all_payslip_generated = cfdi_generated 
   
    
    @api.depends('slip_ids.state')
    def _compute_payslip_cgdi_generated_draft(self):
        cfdi_generated_draft = True
        for payslip in self.slip_ids:
            if payslip.state != 'draft':
                cfdi_generated_draft=False
                break
        self.all_payslip_generated_draft = cfdi_generated_draft 
       

    def enviar_nomina(self):
        self.ensure_one()
        ctx = self._context.copy()
        view = self.env.ref('nomina_cfdi_ee.enviar_nomina_wizard')
        ctx.update({'payslips':self.slip_ids.ids})
  
        return {
            'name': 'Enviar nomina',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'enviar.nomina',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': ctx,
        }

    def timbrar_nomina(self):
        return

    def download_zip(self):
        return {
            'type': 'ir.actions.act_url',
            'url': f'/payroll/download_document?id={self.id}',
            'target': 'new',
        }

    def confirmar_nomina(self):
        self.ensure_one()
        view = self.env.ref('nomina_cfdi_ee.confirmado_nomina_wizard')
        ctx = self.env.context.copy()
        ctx .update({'default_payslip_batch_id':self.id})
        return {
            'name': 'Confirmar Nomina',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'confirmado.de.nomina',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': ctx,
        }

    def confirmar_nomina_wizard(self):
        self.ensure_one()
        #cr = self._cr
        payslip_obj = self.env['hr.payslip']
        start_range = self._context.get('start_range')
        end_range = self._context.get('end_range')
        for payslip_id in self.slip_ids.ids:
            payslip = payslip_obj.browse(payslip_id)
            if start_range and end_range:
                emp_no = int(payslip.employee_id.no_empleado)
                if emp_no >= start_range and emp_no <= end_range:
                    if payslip.state == 'draft':
                        payslip.action_payslip_done()
            else:
                if payslip.state == 'draft':
                   payslip.action_payslip_done()
        return

    @api.onchange('periodicidad_pago', 'date_start')
    def _get_frecuencia_pago(self):
        values = {}
        #if self.freq_pago:
        #    values.update({
        #        'dias_pagar': self.freq_pago.dias_pago,
        #        #'imss_dias': self.freq_pago.dias_cotizar,
        #        })
        if self.date_start and self.dias_pagar:
            fecha_fin = self.date_start + relativedelta(days=self.dias_pagar-1)
            if self.periodicidad_pago == '04':
                if self.date_start.day > 15:
                    date = self.date_start
                    date = date+relativedelta(days=15)
                    month_last_day = monthrange(date.year,date.month)[1]
                    items = [date+relativedelta(day=month_last_day), date+relativedelta(day=15)]
                    previous_month_date = date+relativedelta(months=-1)
                    previous_month_last_day = monthrange(previous_month_date.year,previous_month_date.month)[1]
                    items.append(previous_month_date+relativedelta(day=previous_month_last_day),)
                    if date.day>15:
                        items.append(date+relativedelta(months=1,day=15))
                    fecha_fin = self.nearest_date(items,date)
            values.update({'date_end': fecha_fin})
            self.update(values)
        #if values:
        #    self.update(values)

    @api.model
    def nearest_date(self, items, pivot):
        return min(items, key=lambda x: abs(x - pivot))

    @api.onchange('estructura')
    def _set_aguinaldo_dates(self):
        if self.estructura:
            if self.estructura.name == 'Aguinaldo':
                fecha_fin = datetime(date.today().year, 12, 31)
                fecha_inicio = datetime(date.today().year, 1, 1)
                values = {
                    'date_end': fecha_fin.strftime('%Y-%m-%d'),
                    'date_start': fecha_inicio.strftime('%Y-%m-%d'),
                }
                self.update(values)


class OtrasEntradas(models.Model):
    _name = 'otras.entradas'
    _description = 'OtrasEntradas'

    form_id = fields.Many2one('hr.payslip.run', required=True) 
    monto = fields.Float('Monto') 
    descripcion = fields.Char('Descripcion') 
    codigo = fields.Char('Codigo')

class ConfiguracionNomina(models.Model):
    _name = 'configuracion.nomina'
    _rec_name = "name"
    _description = 'ConfiguracionNomina'

    name = fields.Char(string='Nombre', required=True)
    tipo_pago = fields.Selection(
        selection=[('01', 'Por periodo'), 
                   ('02', 'Por día'),
                   ('03', 'Mes proporcional'),],
        string=_('Conteo de días'),
    )
    fijo_imss = fields.Boolean(string='Dias fijos')
    imss_dias = fields.Float(string='Dias a cotizar en la nómina', store=True)
    imss_mes = fields.Float(string='Dias en el mes', store=True)
    isr_ajustar = fields.Boolean(string='Ajustar ISR en cada nómina', default= True)
    #isr_devolver = fields.Boolean(string='Devolver ISR')
    periodicidad_pago = fields.Selection(
        selection=[('01', 'Diario'), 
                   ('02', 'Semanal'), 
                   ('03', 'Catorcenal'),
                   ('04', 'Quincenal'), 
                   ('05', 'Mensual'),
                   ('06', 'Bimensual'), 
                   ('07', 'Unidad obra'),
                   ('08', 'Comisión'), 
                   ('09', 'Precio alzado'), 
                   ('10', 'Pago por consignación'), 
                   ('99', 'Otra periodicidad'),],
        string=_('Periodicidad de pago CFDI'), required=True
    )

class NominaMessageWizard(models.TransientModel):
    _name = 'nomina.message.wizard'
    _description = "Respuesta timbrado"

    message = fields.Text('Respuesta', required=True)
    log_txt = fields.Text(string='log', default='Sin errores')
    file_data = fields.Binary("File Data")
    nombre = fields.Text(string='nombre', default='Sin errores')

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    def descargar_txt(self):
        self.write({'file_data':base64.b64encode(self.log_txt.encode())})
        action = {
            'name': 'Payslips',
            'type': 'ir.actions.act_url',
            'url': "/web/content/?model="+self._name+"&id=" + str(self.id) + "&field=file_data&download=true&filename=Timbrado_" + self.nombre + ".txt",
            'target': 'self',
            }
        return action
