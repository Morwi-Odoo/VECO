# -*- coding: utf-8 -*-
from odoo import _, fields, models, api
import textwrap
from pytz import timezone


class StockKardexReportWiz(models.TransientModel):
    _name = 'stock.kardex.report.wiz'
    _description = 'Generación de kárdex'

    def _get_category_domain(self):
        products = self.env["product.product"].search([("is_storable", "=", True)])
        categ_ids = products.mapped('categ_id')
        return [('id', 'in', categ_ids.ids)]

    product_ids = fields.Many2many(comodel_name='product.product', string="Productos",
                                   help="Productos que se tomarán en cuenta para la generación del informe")
    location_ids = fields.Many2many(comodel_name='stock.location', string="Ubicaciones", help="Ubicaciones que se tomarán en cuenta para la generación del informe")
    date_from = fields.Datetime(string='De', required=True, default=fields.Datetime.now)
    date_to = fields.Datetime(string='A', required=True, default=fields.Datetime.now)
    company_id = fields.Many2one(comodel_name="res.company", string="Compañía",
                                 default=lambda self: self.env.company.id)
    product_category = fields.Many2many(comodel_name="product.category", string="Categoria", domain=_get_category_domain,
                                        help="Categoria de productos que se tomarán en cuenta para la generación del informe")
    hide_header = fields.Boolean(string="Mostrar en tabla plana",
                                 help="Se mostrará en tabla plana en la generación de informe de excel")
    warehouse_ids = fields.Many2many(comodel_name="stock.warehouse", string="Almacenes")


    # Filtrar por categoría de producto cuando este seleccionada una categoría
    @api.onchange("product_category")
    def domain_products(self):
        for rec in self:
            if rec.product_category:
                return {'domain': {'product_ids': [('company_id', '=', rec.company_id.id),
                                                   ('categ_id', 'in', rec.product_category.ids)]}}
            else:
                return {'domain': {'product_ids':
                                       [('company_id', '=', rec.company_id.id)]}}

    @api.onchange("product_category")
    def check_category(self):
        for rec in self:
            if not rec.product_category:
                rec.product_ids = False
            elif rec.product_ids:
                lines = rec.product_ids.filtered(lambda l:l.categ_id.id in rec.product_category.ids).ids
                rec.product_ids = lines if lines else False

    def create_table(self):
        company_id = self.env.company
        self.env['stock.kardex.report'].sudo().search([('company_id', '=', company_id.id)]).unlink()
        user_tz = self.env.user.tz
        date_from = self.date_from.astimezone(timezone(user_tz))
        date_to = self.date_to.astimezone(timezone(user_tz))
        # Se valida si no hay productos seleccionados (se van a tomar en cuenta todos los de la categoria)
        if not self.product_ids:
            if self.product_category:
                products = self.env['product.product'].sudo().search(
                    [('company_id', '=', company_id.id), ('categ_id', 'in', self.product_category.ids)])
            else:
                products = self.env['product.product'].sudo().search([('company_id', '=', company_id.id)])
        else:
            products = self.product_ids
        if self.warehouse_ids:
            parent_location_ids = self.warehouse_ids.mapped("view_location_id").ids
            location_ids = self.env["stock.location"].sudo().search([("location_id.id","in", parent_location_ids)])
        elif self.location_ids:
            location_ids = self.location_ids
        else:
            location_ids = False

        if location_ids:
            for location in location_ids:
                for product in products:
                    self._cr.execute('''
                    SELECT
                    a.done - b.done
                    AS
                    total
                    FROM
                    (
                        SELECT
                        CASE WHEN sum(quantity) is not null THEN sum(quantity / u.factor * u2.factor) ELSE 0 END as done
                        FROM
                        stock_move_line l
                        left join product_product p on (l.product_id=p.id)
                        left join product_template t on (p.product_tmpl_id=t.id)
                        left join uom_uom u on (u.id=l.product_uom_id)
                        left join uom_uom u2 on (u2.id=t.uom_id)
                        WHERE
                        l.product_id = %s
                        AND
                        l.state = \'done\'
                        AND
                        l.date <= %s
                        AND
                        l.location_dest_id = %s
                    )
                    a
                    CROSS JOIN
                    (
                        SELECT
                        CASE WHEN sum(quantity) is not null THEN sum(quantity / u.factor * u2.factor) ELSE 0 END as done
                        FROM
                        stock_move_line l
                        left join product_product p on (l.product_id=p.id)
                        left join product_template t on (p.product_tmpl_id=t.id)
                        left join uom_uom u on (u.id=l.product_uom_id)
                        left join uom_uom u2 on (u2.id=t.uom_id)
                        WHERE
                        l.product_id = %s
                        AND
                        l.state = \'done\'
                        AND
                        l.date <= %s
                        AND
                        l.location_id = %s                
                    )
                    b
                    ''', [
                        product.id, date_from, location.id,
                        product.id, date_from, location.id,
                    ])
                    start_qty = self._cr.dictfetchall()
                    total = 0
                    if start_qty[0]['total']:
                        total = start_qty[0]['total']
                    self._cr.execute("""WITH one AS (
                        SELECT
                        sml.product_id, sml.product_uom_id,
                        sml.lot_id, sml.owner_id, sml.package_id,
                        sml.quantity, sml.move_id, sml.location_id,
                        sml.location_dest_id, sm.date, sm.origin,sm.reference as move_name,
                        sm.state
                        FROM stock_move_line sml
                        INNER JOIN stock_move sm
                        ON sml.move_id = sm.id
                        WHERE
                        sm.date >= %s
                        AND sm.date <= %s),
                        two AS (
                            SELECT *
                            FROM one
                            WHERE location_id = %s
                            OR location_dest_id = %s)
                        SELECT *
                        FROM two
                        WHERE product_id = %s
                        AND state = 'done'
                        ORDER BY date;""", [
                        date_from, date_to,
                        location.id, location.id,
                        product.id
                    ])
                    moves = self._cr.dictfetchall()
                    report_list = []
                    group_name = '[{}] - {}'.format(location.name, product.display_name)

                    report_list.append({
                        'product_id': product.id,
                        'qty_done': 0,
                        'date': date_from.strftime('%Y-%m-%d %H:%M:%S'),
                        'origin': _('Balance inicial'),
                        'initial_balance': total,
                        'balance': total,
                        'group_name': group_name,
                        'date_from': date_from.strftime('%Y-%m-%d %H:%M:%S'),
                        'date_to': date_to.strftime('%Y-%m-%d %H:%M:%S'),
                        'company_id': company_id.id,
                        'product_uom_id': product.uom_id.id,
                        'location_id': location.id,
                        'location_dest_id': location.id,
                    })
                    initial_balance = total
                    for rec in moves:
                        move_id = self.env["stock.move"].sudo().browse(rec['move_id'])
                        total_cost = move_id.value
                        unit_cost = total_cost / move_id.quantity if move_id.quantity else 0
                        product_uom = self.env['uom.uom'].sudo().search([("id", "=", rec['product_uom_id'])])
                        done_qty = rec['quantity'] / product_uom.factor * product.uom_id.factor
                        if rec['location_id'] == location.id:
                            done_qty = -rec['quantity'] / product_uom.factor * product.uom_id.factor
                        initial_total = initial_balance
                        total += done_qty
                        initial_balance = total
                        origin = rec['origin']
                        if origin:
                            origin = textwrap.shorten(
                                rec['origin'], width=80, placeholder="...")
                        else:
                            origin = textwrap.shorten(
                                rec['move_name'], width=80, placeholder="...")
                        if (self.warehouse_ids and move_id.is_valued) or (not self.warehouse_ids):
                            line = {
                                'move_id': rec['move_id'],
                                'product_id': rec['product_id'],
                                'product_uom_id': product.uom_id.id,
                                'lot_id': rec['lot_id'],
                                'owner_id': rec['owner_id'],
                                'package_id': rec['package_id'],
                                'qty_done': done_qty,
                                'location_id': rec['location_id'],
                                'location_dest_id': rec['location_dest_id'],
                                'date': rec['date'],
                                'initial_balance': initial_total,
                                'balance': total,
                                'origin': origin,
                                'group_name': group_name,
                                'date_from': date_from.strftime('%Y-%m-%d %H:%M:%S'),
                                'date_to': date_to.strftime('%Y-%m-%d %H:%M:%S'),
                                'company_id': company_id.id,
                                'unit_cost': unit_cost,
                                'total_cost': total_cost
                            }
                            report_list.append(line)
                    self.env['stock.kardex.report'].create(report_list)
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'message': _('Es necesario seleccionar un almacén o una ubicación.'),
                }
            }


    def print_report(self):
        error = self.create_table()
        if error:
            return error
        return self.env.ref('stock_kardex_report.stock_kardex_report_action').report_action(self)

    def create_report_xlsx(self):
        error = self.create_table()
        if error:
            return error
        return self.env.ref('stock_kardex_report.stock_kardex_report_xlsx').report_action(self)

    def open_view(self):
        error = self.create_table()
        if error:
            return error
        tree_view_id = self.env.ref('stock_kardex_report.stock_kardex_report_tree_view').id
        form_view_id = self.env.ref('stock_kardex_report.stock_kardex_report_form_view').id
        search_id = self.env.ref('stock_kardex_report.stock_kardex_report_search').id
        domain = []
        if self.warehouse_ids:
            domain = [("unit_cost","!=", 0), ("total_cost","!=", 0) ]
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'list'),(form_view_id, 'form')],
            'view_id': tree_view_id,
            'search_view_id': search_id,
            'view_mode': 'list,form',
            'name': _('Kardex de inventario'),
            'res_model': 'stock.kardex.report',
            'domain': domain,
            'context': {"search_default_group": 1}
        }
        return action
