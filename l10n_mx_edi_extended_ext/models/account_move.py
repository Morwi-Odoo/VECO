# -*- coding: utf-8 -*-
from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _l10n_mx_edi_add_invoice_cfdi_values(self, cfdi_values):
        # EXTENDS 'l10n_mx_edi_extended'
        super()._l10n_mx_edi_add_invoice_cfdi_values(cfdi_values)

        comercio_exterior = cfdi_values.get('comercio_exterior')
        if not comercio_exterior:
            return

        desc_especifica_by_code = {}
        for base_line in cfdi_values['base_lines']:
            line = base_line['record']
            info = line.info_mercancias
            if not info:
                continue
            entries = desc_especifica_by_code.setdefault(base_line['product_id'].default_code, [])
            if info.cce_series:
                for serie in info.cce_series:
                    entries.append({
                        'Marca': info.cce_marca,
                        'Modelo': info.cce_modelo,
                        'SubModelo': info.cce_submodelo,
                        'NumeroSerie': serie.cce_numeroserie,
                    })
            else:
                entries.append({
                    'Marca': info.cce_marca,
                    'Modelo': info.cce_modelo,
                    'SubModelo': info.cce_submodelo,
                    'NumeroSerie': None,
                })

        for mercancia in comercio_exterior['mercancia_list']:
            mercancia['desc_especifica'] = desc_especifica_by_code.get(mercancia['no_identificacion'], [])
