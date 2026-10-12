# -*- coding: utf-8 -*-
# © 2021 Morwi Encoders Consulting SA DE CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from datetime import date, datetime

from odoo import models, fields, api


class MrpProductionPlanItem(models.Model):
    _name = "mrp.production.plan.item"

    # Hidden helper fields
    sale_line_id = fields.Many2one(
        'sale.order.line',
        index=True,
    )
    # Sale Fields
    in_date = fields.Date(
        'Reception Date',  # Ingreso
        default=fields.Date.today,
    )
    sale_id = fields.Many2one(
        'sale.order',
        related="sale_line_id.order_id",
        string='Sale Order',  # Venta
        index=True,
        store=True,
    )
    partner_id = fields.Many2one(
        related="sale_line_id.order_id.partner_id",
        string="Customer",
        store=True,
        index=True,
    )
    product_id = fields.Many2one(
        related="sale_line_id.product_id",
        string='Description',
        store=True,
        index=True,
    )
    qty_to_produce = fields.Float(
        related="sale_line_id.product_uom_qty",
        string='Quantity to Produce',  # SOL.
        help="Qty to produce in Manufacture Orders",
        store=True,
    )
    uom = fields.Many2one(
        related="sale_line_id.product_uom_id",
        string='UoM',  # UM
        store=True,
    )
    planned_date = fields.Datetime(
        related="sale_id.date_order",
        string="Approval Date",  # Fecha aprobación
        store=True,
    )
    sale_date = fields.Datetime(
        related="sale_id.commitment_date",
        string='Commitment Sale Date',  # Fecha promesa de ventas
        store=True,
    )
    family = fields.Selection(
        related="product_id.x_studio_lnea_produccin",
        string='Product Family',
        store=True,
        index=True,
    )  # Familia
    # MRP Fields
    comp_date = fields.Datetime(
        related="sale_line_id.plant_commitment_date",
        string='Factory Commitment Date',  # Compromiso en planta
        readonly=False,
        store=True,
    )
    mrp_id = fields.Many2one(
        'mrp.production',
        string='Production',
        index=True,
    )  # Órden de producción
    mrp_date = fields.Datetime(
        related="mrp_id.x_studio_fecha_inicio_fabrticacion",
        string='Production Date',  # Fecha de fabricación
        store=True,
        readonly=False,
    )
    pack = fields.Char()
    # Sub Productos
    subproduct_line_ids = fields.One2many(
        'mrp.production.plan.subproduct.line',
        'plan_id',
        string="Sub Products",
        readonly=True,
    )
    # MRP
    status = fields.Selection(
        related="mrp_id.x_studio_estatus_de_produccin",
        string='Production State',  # Estatus producción
        readonly=False,
        store=True,
    )
    client_delivery_date = fields.Datetime(
        'Customer Delivery Date')  # Fecha de entrega al cliente
    client_delivery_date_formatted = fields.Char(
        compute='_compute_client_delivery_date_formatted',
        store=True,
    )
    invoice_list = fields.Char(
        string='Invoice',  # N. Factura
    )
    delay = fields.Char()  # Retraso
    completed = fields.Boolean()  # Completo
    # Campos calculados (fechas)
    delay_days = fields.Integer(
        default=0,  # Días entre ingreso y entrega
        compute="_compute_dates",
        store=True,
    )
    sale_time = fields.Integer(
        default=0,  # Tiempo que ventas deja para fabricar el producto
        compute="_compute_dates",
        store=True,
    )
    plant_time = fields.Integer(
        default=0,  # Tiempo que planta ofrecio para ese producto en la semana que entro el pedido
        compute="_compute_dates",
        store=True,
    )
    # Campos calculados (char)
    prod_delay_warehouse = fields.Char(
        'MRP - Warehouse Delay',  # Retraso Prod vs Almacén
        readonly=False,
        compute='_get_prod_delay',
        store=True,
    )
    production = fields.Boolean(
        'Produced',  # Producción
        compute='_get_prod_delay',
        store=True,
    )
    is_delivery = fields.Boolean(
        'Delivered',  # Entregado
        compute='_get_prod_delay',
        store=True,
    )
    #
    diff_days_delivery = fields.Integer(
        'Warehouse - Delivery Delay',
        compute='_get_delivery_client_delay',  # Entrega Almacén vs Fecha Promesa
        store=True,
    )
    full_delivered = fields.Boolean(
        'Fully Delivered',
        compute='_get_delivery_client_delay',
        store=True,
    )  # Entregado 100%

    # def _compute_mrp_date(self):
    #     for rec in self:
    #         rec.mrp_date = (
    #             rec.mrp_id.x_studio_fecha_inicio_fabrticacion or
    #             rec.mrp_id.date_planned_start)

    @api.depends('sale_line_id', 'sale_id')
    def _compute_client_delivery_date_formatted(self):
        for rec in self:
            result = ""
            for picking in rec.sale_line_id.order_id.picking_ids.filtered(
                    lambda p: p.state == 'done' and
                    p.picking_type_code == 'outgoing'):
                result += ("%s - %s \n" % (
                    picking.name, picking.date_done.strftime(
                        '%d-%m-%Y %H:%M:%S')))
            rec.client_delivery_date_formatted = result

    def _get_delivery_client_delay(self):
        for item in self:
            # 'Warehouse - Commitment Delivery Date
            # If the date done is greather than sale commitment date
            # pyshical income date - sale delivery date
            # if pyshical receipt is not done the estate will be PEND
            promise_date = item.sale_date
            value = 'OT'
            full_delivered = all(
                pick.state in ['done', 'cancel'] for pick in
                item.sale_id.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'outgoing'))
            if not item.client_delivery_date or not promise_date:
                value = 'PEND'
            elif item.client_delivery_date > promise_date:
                value = item.get_diff_dates(
                    item.client_delivery_date, item.sale_date
                )
            item.update({
                'full_delivered': full_delivered,
                'diff_days_delivery': value if value not in ['OT', 'PEND'] else 0,
            })

    def _get_prod_delay(self):
        for item in self:
            # MRP - Warehouse Delay
            # If the reception date is greather than commitment date
            # pyshical income date - sale date
            # if pyshical receipt is not done the estate will be PEND
            promise_date = item.sale_date
            value = 'OT'
            for hability in item.subproduct_line_ids:
                if not hability.hability_incomming_date or not promise_date:
                    value = 'PEND'
                elif hability.hability_incomming_date > promise_date:
                    value = str(
                        item.get_diff_dates(
                            hability.hability_incomming_date, item.sale_date
                            )
                        )

            item.update({
                'production': value == 'OT',
                'prod_delay_warehouse': value,
                'is_delivery': item.status == "c. Facturado/Entregado",
            })

    @api.depends('client_delivery_date', 'in_date',
                 'sale_date', 'comp_date', 'sale_id')
    def _compute_dates(self):
        for item in self:
            item.update({
                'delay_days': abs(
                    item.get_diff_dates(
                        item.client_delivery_date, item.in_date)),
                'sale_time': abs(
                    item.get_diff_dates(
                        item.sale_id.date_order, item.sale_date)),
                'plant_time': abs(
                    item.get_diff_dates(
                        item.sale_id.date_order, item.comp_date)),
            })

    def name_get(self):
        result = []
        for rec in self:
            name = rec.product_id.display_name + ' - ' + rec.mrp_id.name
            if rec.sale_id:
                name += ' - ' + rec.sale_id.name
            result.append((rec.id, name))
        return result

    def get_diff_dates(self, date1, date2):
        if isinstance(date1, date):
            date1 = datetime.combine(date1, datetime.min.time())

        if isinstance(date2, date):
            date2 = datetime.combine(date2, datetime.min.time())

        if not date1 or not date2:
            return 0
        return (date1 - date2).days

    def _create_items(self):
        production_items = self
        # self.search([]).unlink()
        current_rows = self.search([])
        # Create transient records based on sale orders and manufacture orders
        sale_domain = [('state', 'in', ['sale', 'done'])]
        StockMove = self.env['stock.move'].sudo()
        AccountInvoice = self.env['account.move'].sudo()
        current_sol = current_rows.mapped('sale_line_id')
        if current_rows and current_sol:
            sale_domain.append(
                ('id', 'not in', current_sol.ids))

        sale_line_ids = self.env['sale.order.line'].search(sale_domain)
        mrp_orders = self.env['mrp.production'].search(
            [('state', '!=', 'cancel'),
             ('id', 'not in', current_rows.mapped('mrp_id.id')),
             ('product_id.bom_line_ids', '=', False)]
        )
        for mrp in mrp_orders:
            sale_line_ids = (
                mrp.x_studio_sale_id.order_line.filtered(
                    lambda line: line.product_id == mrp.product_id) or
                sale_line_ids.filtered(
                    lambda line: line.product_id == mrp.product_id and
                    line.order_id.name == mrp.origin)
            )
            if not sale_line_ids:
                continue
            sale_line = sale_line_ids[:1]
            if sale_line in current_sol:
                continue
            if sale_line.product_uom_qty == sale_line.qty_delivered:
                continue
            sale_picking = sale_line.move_ids.filtered(
                lambda move: move.picking_id.state == 'done' and
                move.picking_code == 'outgoing')
            sale_picking_date_done = False
            if sale_picking:
                sale_picking_date_done = sale_picking[-1].picking_id.date_done

            invoice_ids = sale_line.invoice_lines.mapped('move_id').filtered(
                lambda invoice: invoice.state not in ['draft', 'cancel'])
            dest_location = mrp.location_dest_id
            sfp_pick = (
                mrp.picking_ids.filtered(
                    lambda x: x.location_id == dest_location)
                or sale_line.order_id.picking_ids.filtered(
                    lambda x: x.location_id == dest_location)
            )
            incomming_date = False
            if sfp_pick:
                incomming_date = sfp_pick[:1].date_done
            values = {
                'sale_line_id': sale_line.id,
                'mrp_id': mrp.id,
                'client_delivery_date': sale_picking_date_done,
                'invoice_list': ', '.join(
                    invoice_ids.mapped('display_name')),
                'in_date': incomming_date,
                'completed': all(
                    pick.state in ['done', 'cancel'] for pick in sfp_pick),
            }

            hability_mrp_ids = self.env['mrp.production'].search(
                [('origin', '=', mrp.name)])
            hability_lines = []
            for hability_mrp_id in hability_mrp_ids:
                dest_location = hability_mrp_id.location_dest_id
                hability_sfp_picking = (
                    hability_mrp_id.picking_ids.filtered(
                        lambda x: x.location_id == dest_location)
                )
                incomming_date = False
                if hability_sfp_picking:
                    incomming_date = (
                        hability_sfp_picking[:1].date_done)
                hability_lines.append((0, 0, {
                    'hability_mrp_id': hability_mrp_id.id,
                    'hability_incomming_date': incomming_date,
                }))
            if hability_lines:
                values['subproduct_line_ids'] = hability_lines
            if values['sale_line_id'] not in current_sol.ids:
                production_items += self.create(values)
        return production_items + current_rows

    @api.model
    def run_production_plan(self):
        production_items = self._create_items()
        action = self.env.ref(
            'mrp_production_plan.action_view_production_plan_show').read()[0]
        action['domain'] = [('id', 'in', production_items.ids)]
        return action


class MrpProductionPlanSubproductLine(models.Model):
    _name = 'mrp.production.plan.subproduct.line'
    _description = 'Mrp Production Plan SubProduct Line'

    plan_id = fields.Many2one(
        'mrp.production.plan.item',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    hability_mrp_id = fields.Many2one(
        'mrp.production',
        string='Sub Product Production')  # Órden de habilitado
    hability_product_id = fields.Many2one(
        related="hability_mrp_id.product_id",
        string='Sub Product',  # Código de habilitado
        store=True,
    )
    hability_qty = fields.Float(
        related="hability_mrp_id.product_qty",
        string="Quantity",
        default=0,
    )
    hability_dimension = fields.Text(
        related="hability_mrp_id.product_id.description_pickingin",
        string="Dimensions"
    )
    hability_incomming_date = fields.Datetime(
        'Physical Income Date')  # Ingreso Físico al almacén
