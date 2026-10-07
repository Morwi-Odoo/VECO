# -*- coding: utf-8 -*-
# © 2020 Morwi Encoders Consulting SA DE CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def button_start(self):
        """Method Overriden to avoid the activity creation
           when start the workorder"""

        self.ensure_one()
        res = super(MrpWorkorder, self).button_start()
        TimeLine = self.env['mrp.workcenter.productivity']
        if self.state in ('done', 'cancel'):
            return True

        # As button_start is automatically called in the new view
        if self.state in ('done', 'cancel'):
            return True

        if self.production_id.state != 'progress':
            self.production_id.write({
                'state': 'progress',
                'date_start': fields.Datetime.now(),
            })
        if self.state == 'progress':
            return True
        else:
            start_date = fields.Datetime.now()
            vals = {
                'state': 'progress',
                'date_start': start_date,
                'date_planned_start': start_date,
            }
            if self.date_planned_finished and self.date_planned_finished < start_date:
                vals['date_planned_finished'] = start_date
            self.write(vals)
        return res

    # def _compute_working_users(self):
    #     for order in self:
    #         order.is_user_working = True

    def open_tablet_view(self):
        res = super(MrpWorkorder, self).open_tablet_view()
        self.button_start()
        return res


class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"

    workforce_entry_id = fields.Many2one(
        comodel_name='account.move',
        string='Workforce Journal Entry',
    )

    @api.constrains('date_start', 'date_end')
    def _validate_date_range(self):
        for rec in self:
            if (rec.date_start and rec.date_end and
                    rec.date_start > rec.date_end):
                raise ValidationError(
                    _('Error! The start date must be lower than the date end.')
                )

    def get_account_move(self):
        self.ensure_one()
        action = self.env.ref('account.action_move_journal_line').read()[0]
        action.update({
            'context': {
                'create': False,
                'delete': False,
            },
            'domain': [('id', '=', self.workforce_entry_id.id)],
        })
        return action

    @api.model
    def get_operation_amount(self):
        cost_hour = self.workcenter_id.costs_hour
        duration = self.duration / 60.0
        return round(duration * cost_hour, 2)

    @api.model
    def _prepare_workforce_lines(self, journal_id,
                                 main_account_id, accounts_data):
        lines = []
        amount = self.get_operation_amount()
        balance_amount = 0.0
        # Create balance lines
        aml_name = (_('WorkForce ') + self.workorder_id.display_name)
        # Main journal Entry
        lines.append((0, 0, {
            'name': aml_name,
            'debit': amount,
            'credit': 0.0,
            'currency_id': self.env.company.currency_id.id,
            'journal_id': journal_id.id,
            'account_id': main_account_id.id,
            'mrp_timeline_id': self.id,
        }))
        for aml_line in accounts_data:
            line_amount = round(amount * (aml_line.percentage / 100), 2)
            balance_amount += line_amount
            # If is the las line the journal entry will be balanced
            if aml_line == accounts_data[-1]:
                difference = amount - balance_amount
                if difference:
                    line_amount += difference
            lines.append((0, 0, {
                'name': aml_name,
                'debit': 0.0,
                'credit': line_amount,
                'currency_id': self.env.company.currency_id.id,
                'journal_id': journal_id.id,
                'account_id': aml_line.account_id.id,
                'mrp_timeline_id': self.id,
            }))
        return lines

    @api.model
    def create_workforce_entry(self):
        AccountMove = self.env['account.move']

        # Validates the data needed to make the account move
        mrp_warehouse = self.env['stock.warehouse'].search([
            ('manu_type_id', '=',
                self.workorder_id.production_id.picking_type_id.id)])
        main_account_id = mrp_warehouse.workforce_account_id
        accounts_data = mrp_warehouse.workforce_account_ids
        journal_id = mrp_warehouse.workforce_cost_journal_id
        if not main_account_id or not accounts_data or not journal_id:
            raise ValidationError(
                _('Error! You must configure the workforce'
                    ' accounts and journal on the Warehouse'))
        date = self.date_end.date()
        lines = self. _prepare_workforce_lines(
            journal_id, main_account_id, accounts_data)
        # If the user edits the time
        # line we only modify the existing journal entry
        if self._context.get('is_edition'):
            lines.extend([
                (2, line.id) for line in self.workforce_entry_id.line_ids])
            self.workforce_entry_id.button_cancel()
            try:
                self.workforce_entry_id.write({
                    'date': date,
                    'line_ids': lines,
                })
            except Exception as e:
                raise ValidationError(
                    e.name + _('\n The MO with the problem is: %s') % (
                        self.workorder_id.production_id.name))
            self.workforce_entry_id.action_post()
            return self.workforce_entry_id
        # Create the new move
        try:
            move = AccountMove.create({
                'journal_id': journal_id.id,
                'date': date,
                'state': 'draft',
                'line_ids': lines,
                'ref': self.workorder_id.display_name,
                'mrp_timeline_id': self.id,
                'move_type': 'entry',
            })
        except Exception as e:
            raise ValidationError(
                _('\n The MO with the problem is: %s \n'
                    'Workorder: %s \n'
                    'Time Record: Date Start: %s - Date End: %s \n'
                    'User: %s \n Error: %s') % (
                    self.workorder_id.production_id.name,
                    self.workorder_id.display_name,
                    self.date_start,
                    self.date_end,
                    self.user_id.name,
                    str(e))
                )

        self.workforce_entry_id = move.id
        move.action_post()

    @api.model_create_multi
    def create(self, vals_list):
        res = super(MrpWorkcenterProductivity, self).create(vals_list)
        create_record = False
        for vals in vals_list:
            if vals.get('date_start') and vals.get('date_end'):
                create_record = True
                break
        if create_record:
            for record in res:
                record.create_workforce_entry()
        return res

    def write(self, vals):
        res = super(MrpWorkcenterProductivity, self).write(vals)
        if vals.get('workforce_entry_id'):
            return res

        for rec in self:
            # Update the data
            if rec.workforce_entry_id:
                is_edition = True
            else:
                is_edition = False
                rec.with_context(is_edition=is_edition).create_workforce_entry()
        return res

    def unlink(self):
        for rec in self:
            rec.workforce_entry_id.button_draft()
            rec.workforce_entry_id.button_cancel()
            rec.workforce_entry_id.with_context(force_delete=True).unlink()
