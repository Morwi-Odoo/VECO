# -*- coding: utf-8 -*-
from odoo import fields, models

class StockKardexReport(models.Model):
    _name = 'stock.kardex.report'
    _description = 'Kárdex de inventario'

    move_id = fields.Many2one('stock.move', readonly=True)
    product_id = fields.Many2one('product.product', string="Producto",readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string="UoM", readonly=True)
    lot_id = fields.Many2one('stock.lot', readonly=True)
    owner_id = fields.Many2one('res.partner', string="Lote/N° de serie", readonly=True)
    package_id = fields.Many2one('stock.package', readonly=True)
    location_id = fields.Many2one('stock.location', string="Ubicación origen", readonly=True)
    location_dest_id = fields.Many2one('stock.location', string="Ubicación destino", readonly=True)
    qty_done = fields.Float('Cantidad hecha', readonly=True)
    date = fields.Datetime(string="Fecha", readonly=True)
    date_from = fields.Datetime(string='De', readonly=True)
    date_to = fields.Datetime(string='A', readonly=True)
    origin = fields.Char(string="Origen", readonly=True)
    initial_balance = fields.Float(string="Balance inicial", readonly=True)
    balance = fields.Float(string="Balance final", readonly=True)
    group_name = fields.Char(string="Grupo")
    company_id = fields.Many2one(comodel_name="res.company", string="Compañía", default=lambda self: self.env.company.id)
    categ_id = fields.Many2one('product.category', string="Categoría de producto", readonly=True)
    unit_cost = fields.Float(string="Costo unitario")
    total_cost = fields.Float(string="Valor total")

