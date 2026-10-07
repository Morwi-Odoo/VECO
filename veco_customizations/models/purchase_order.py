# -*- coding: utf-8 -*-
# © 2020 Morwi Encoders Consulting SA DE CV
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def _prepare_invoice(self):
        result = super(PurchaseOrder, self)._prepare_invoice()
        move_type = self._context.get('default_move_type', 'in_invoice')
        journals = self.env['account.move']._get_suitable_journal_ids(move_type, self.company_id)
        if journals:
            result['journal_id'] = journals[0].id
        return result
