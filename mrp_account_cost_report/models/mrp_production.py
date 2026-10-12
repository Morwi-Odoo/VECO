# -*- coding: utf-8 -*-
# © 2021 Morwi Encoders Consulting SA DE CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging

from collections import Counter


from odoo import api, fields, models
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class MRPProduction(models.Model):
    _inherit = 'mrp.production'

    components_amount = fields.Float(
        compute='_compute_costs',
        store=True,
    )
    workforce_amount = fields.Float(
        compute='_compute_costs',
        store=True,
    )
    indirects_amount = fields.Float(
        compute='_compute_costs',
        store=True,
    )
    hours = fields.Float(
        compute='_compute_costs',
        store=True,
    )
    total_cost = fields.Float(
        compute='_compute_costs',
        store=True,
    )
    unit_cost = fields.Float(
        compute='_compute_costs',
        store=True,
    )
    sale_amount = fields.Float(
        compute='_compute_sale_amount',
        store=True,
    )
    sale_price_unit = fields.Float(
        compute='_compute_sale_amount',
        store=True,
    )
    components_percentage = fields.Float(
        compute='_compute_cost_percentages',
        store=True,
    )
    workforce_percentage = fields.Float(
        compute='_compute_cost_percentages',
        store=True,
    )
    indirects_percentage = fields.Float(
        compute='_compute_cost_percentages',
        store=True,
    )
    qty_done = fields.Float(
        digits='Product Unit of Measure',
        compute='_compute_qty_done', store=True,)
    factor = fields.Float(
        compute='_compute_sale_amount',
        store=True,
    )
    x_studio_cliente_p_1 = fields.Char()

    @api.depends('state')
    def _compute_costs(self):
        counter = 0
        self.write({
            'components_amount': 0.0,
            'workforce_amount': 0.0,
            'indirects_amount': 0.0,
            'hours': 0.0,
        })
        for rec in self:
            counter += 1
            _logger.info(
                "MRP Manufacture computed method _compute_costs"
                " executing %s record of %s ", counter, len(self))
            to_write = {
                'components_amount': 0.0,
                'workforce_amount': 0.0,
                'indirects_amount': 0.0,
                'hours': 0.0,
            }

            # Components
            raw_material_moves = []
            production_ids = rec.ids
            backorders = rec.procurement_group_id.mrp_production_ids
            if backorders and rec.product_tracking in ['lot', 'serial']:
                production_ids = backorders.ids
            currency_table = (
                self.env['res.currency']._get_query_currency_table({
                    'multi_company': True,
                    'date': {
                        'date_to': fields.Date.today()
                        }
                    }
                ))
            query_str = """SELECT
                                abs(SUM(svl.quantity)),
                                abs(SUM(svl.value)),
                                currency_table.rate
                       FROM stock_move AS sm
                       INNER JOIN stock_valuation_layer
                            AS svl ON svl.stock_move_id = sm.id
                       LEFT JOIN mrp_production
                            AS mo on sm.raw_material_production_id = mo.id
                       LEFT JOIN {currency_table} ON
                                currency_table.company_id = mo.company_id
                       WHERE sm.raw_material_production_id in %s
                            AND sm.state != 'cancel'
                            AND sm.product_qty != 0
                            AND scrapped != 't'
                       GROUP BY currency_table.rate""".format(
                            currency_table=currency_table,)
            self.env.cr.execute(query_str, (tuple(production_ids), ))
            total_cost = 0
            for qty, cost, currency_rate in self.env.cr.fetchall():
                if cost is None:
                    cost = 0
                cost *= currency_rate
                to_write['components_amount'] += cost

            # Workforce & Indirects Amount
            Workorders = self.env['mrp.workorder'].search(
                [('production_id', 'in', rec.ids)])
            for work_line in Workorders.mapped('time_ids'):
                if work_line.workforce_entry_id.line_ids:
                    to_write['workforce_amount'] += abs(
                        work_line.workforce_entry_id.line_ids[0].balance)
                    to_write['indirects_amount'] += abs(
                        work_line.workforce_entry_id.line_ids[1].balance)
                to_write['hours'] += (work_line.duration / 60)

            # Ensure amount in case of past backorder manufacture
            if float_is_zero(to_write['workforce_amount'], precision_digits=2) and backorders:
                to_write['workforce_amount'] = max(
                    backorders.mapped('workforce_amount'))
                to_write['hours'] = max(backorders.mapped('hours'))
                to_write['indirects_amount'] = max(
                    backorders.mapped('indirects_amount'))

            # Ensure field value to values with 0
            for field, field_value in to_write.items():
                if float_is_zero(field_value, precision_digits=2):
                    to_write[field] = rec._get_most_repeated_field_value(
                        field)

            to_write['total_cost'] = (
                to_write['components_amount'] + to_write['workforce_amount'] +
                to_write['indirects_amount'])
            total_qty = (rec.product_qty or 1)
            if backorders:
                total_qty = sum(backorders.mapped('product_qty')) or 1
            to_write['unit_cost'] = to_write['total_cost'] / total_qty

            rec.update(to_write)

    def _get_most_repeated_field_value(self, field):
        self.ensure_one()
        try:
            values = self.search_read(
                [('product_id', '=', self.product_id.id),
                 ('state', '=', 'done'),
                 (field, '>', 0)], [field])
            occurence_count = Counter([val[field] for val in values])
            return occurence_count.most_common(1)[0][0]
        except Exception as e:
            return 0

    @api.depends('state')
    def _compute_sale_amount(self):
        counter = 0
        for rec in self:
            counter += 1
            _logger.info(
                "MRP Manufacture computed method _compute_sale_amount"
                " executing %s record of %s: ", counter, len(self))
            lines = self.env['sale.order.line'].search(
                [('product_id', '=', rec.product_id.id),
                 ('order_id', '=', rec.x_studio_sale_id.id)])
            rec.update({
                'sale_price_unit': sum(lines.mapped('price_subtotal')) / (sum(
                    lines.mapped('product_uom_qty')) or 1),
                'sale_amount': sum(lines.mapped('price_subtotal')),
                'factor': (sum(lines.mapped('price_subtotal')) / (sum(
                    lines.mapped('product_uom_qty')) or 1)) / (rec.unit_cost or 1),
            })

    @api.depends('components_amount', 'workforce_amount', 'indirects_amount')
    def _compute_cost_percentages(self):
        for rec in self:
            rec.update({
                'components_percentage': rec.components_amount * 100 / (
                    rec.total_cost or 1),
                'workforce_percentage': rec.workforce_amount * 100 / (
                    rec.total_cost or 1),
                'indirects_percentage': rec.indirects_amount * 100 / (
                    rec.total_cost or 1),
            })

    @api.depends('state', 'finished_move_line_ids')
    def _compute_qty_done(self):
        for rec in self:
            rec.qty_done = sum(rec.finished_move_line_ids.mapped('qty_done'))

    def refresh_costs(self):
        init_date = fields.Datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0)
        end_date = fields.Datetime.now().replace(
            hour=23, minute=59, second=59)
        orders = self.search([
            ('date_finished', '>=', init_date),
            ('date_planned_finished', '<=', end_date),
            ('state', '=', 'done')])
        orders._compute_costs()
