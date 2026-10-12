# -*- coding: utf-8 -*-
# © 2020 Morwi Encoders Consulting SA DE CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def action_product_forecast(self):
        self.ensure_one()
        ProductForecastReport = self.env['product.forecast.report']
        ProductForecastReport.search(
            [('product_id', 'in', self.mapped('product_variant_ids').ids),
             ('user_id', '=', self.env.user.id)]).unlink()

        variants_available = self.mapped(
            'product_variant_ids')._get_forecast_detail()
        return self.mapped('product_variant_ids').generate_forecast_report(
            variants_available)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def generate_forecast_report(self, variants_available):
        self.ensure_one()
        ProductForecastReport = self.env['product.forecast.report']
        to_create = []
        for product_id, items in variants_available.items():
            # Quant
            for quant in items.get('quants'):
                to_create.append({
                    'line_type': 'on_hand',
                    'product_id': product_id,
                    'product_qty': quant.quantity,
                    'product_uom': quant.product_uom_id.id,
                    'stock_move_id': False,
                    'location_id': quant.location_id.id,
                    'location_dest_id': False,
                    'state': False,
                    'lot_id': quant.lot_id.id,
                })
            # Moves In
            if not items.get('moves_in'):
                to_create.append({
                    'line_type': 'incoming',
                    'product_id': product_id,
                    'product_qty': 0.0,
                    'product_uom': self.uom_id.id,
                })
            for move in items.get('moves_in'):
                to_create.append({
                    'line_type': 'incoming',
                    'product_id': product_id,
                    'product_qty': move.product_qty,
                    'product_uom': move.product_uom.id,
                    'stock_move_id': move.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'state': move.state,
                    'picking_id': move.picking_id.id,
                })
            if not items.get('moves_out'):
                to_create.append({
                    'line_type': 'outgoing',
                    'product_id': product_id,
                    'product_qty': 0.0,
                    'product_uom': self.uom_id.id,
                })
            # Moves Out
            for move in items.get('moves_out'):
                to_create.append({
                    'line_type': 'outgoing',
                    'product_id': product_id,
                    'product_qty': -move.product_qty,
                    'product_uom': move.product_uom.id,
                    'stock_move_id': move.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'state': move.state,
                    'picking_id': move.picking_id.id,
                })
        report_lines = ProductForecastReport.create(to_create)

        action = {
            'name': _('Forecast Report'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': ProductForecastReport._name,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', report_lines.ids)],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
                'search_default_line_type_groupby': True,
            }
        }
        return action

    def action_product_forecast(self):
        self.ensure_one()
        ProductForecastReport = self.env['product.forecast.report']
        ProductForecastReport.search(
            [('product_id', '=', self.id),
             ('user_id', '=', self.env.user.id)]).unlink()

        variants_available = self._get_forecast_detail()
        return self.generate_forecast_report(variants_available)

    def _get_forecast_detail(self):
        # Super call
        domain_quant_loc, domain_move_in_loc, domain_move_out_loc = (
            self._get_domain_locations())
        # Do not take care of output, pack & input locations in quant domain
        wrong_locations = self.env['stock.location']
        for warehouse in self.env['stock.warehouse'].search([]):
            wrong_locations |= warehouse.wh_input_stock_loc_id
            wrong_locations |= warehouse.wh_output_stock_loc_id
            wrong_locations |= warehouse.wh_pack_stock_loc_id

        domain_quant = ([('product_id', 'in', self.ids),
                        ('location_id', 'not in', wrong_locations.ids)] +
                        domain_quant_loc)
        domain_move_in = [
            ('product_id', 'in', self.ids)] + domain_move_in_loc
        domain_move_out = [
            ('product_id', 'in', self.ids)] + domain_move_out_loc

        Move = self.env['stock.move']
        Quant = self.env['stock.quant']
        domain_move_in_todo = [
            ('state', 'in', ('waiting', 'confirmed',
                             'assigned', 'partially_available'))
        ] + domain_move_in
        domain_move_out_todo = [(
            'state', 'in', ('waiting', 'confirmed', 'assigned',
                            'partially_available'))] + domain_move_out
        moves_in_res = {}
        moves_out_res = {}
        quants_res = {}
        for item in Move.search(domain_move_in_todo):
            moves_in_res.setdefault(item.product_id.id, []).append(item)
        for item in Move.search(domain_move_out_todo):
            moves_out_res.setdefault(item.product_id.id, []).append(item)
        for item in Quant.search(domain_quant):
            quants_res.setdefault(item.product_id.id, []).append(item)

        res = dict()
        for product in self.with_context(prefetch_fields=False):
            product_id = product.id
            rounding = product.uom_id.rounding
            res[product_id] = {
                'quants': quants_res.get(product_id, {}),
                'moves_in': moves_in_res.get(product_id, {}),
                'moves_out': moves_out_res.get(product_id, {}),
            }
        return res


class ProductForecastReport(models.Model):
    _name = 'product.forecast.report'
    _description = 'Product Forecast Report'

    line_type = fields.Selection(
        [('on_hand', 'On Hand'),
         ('incoming', 'Incoming'),
         ('outgoing', 'Outgoing')],
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        readonly=True,
    )
    product_qty = fields.Float(
        'Product Quantity',
        digits='Product Unit',
    )
    product_uom = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit of Measure',
    )
    lot_id = fields.Many2one(
        comodel_name='stock.lot',
        string='Lot/Serial Number',
        readonly=True)
    stock_move_id = fields.Many2one(
        comodel_name='stock.move',
        readonly=True,
    )
    picking_id = fields.Many2one(
        comodel_name='stock.picking',
        readonly=True,)
    location_id = fields.Many2one(
        comodel_name='stock.location',
        readonly=True,
    )
    location_dest_id = fields.Many2one(
        comodel_name='stock.location',
        string='Destination Location',
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'New'), ('cancel', 'Cancelled'),
        ('waiting', 'Waiting Another Move'),
        ('confirmed', 'Waiting Availability'),
        ('partially_available', 'Partially Available'),
        ('assigned', 'Available'),
        ('done', 'Done')], string='Status',
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        default=lambda s: s.env.user,
    )
