# Copyright 2017, Vauxoo, Jarsa Sistemas, S.A. de C.V.
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import _, api, exceptions, fields, models


def assert_xunnel_token(function):
    """Raises an user error whenever the user
    tries to manual update either providers or invoices
    without having any Xunnel Token registered in its company.
    """
    def wraper(self):
        if not self.company_id.xunnel_token and not self.env.company.xunnel_token:
            raise exceptions.UserError(_(
                "Your company doesn't have a Xunnel Token "
                "established. Please add one before trying manual sync."))
        return function(self)
    return wraper


class AccountConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    xunnel_token = fields.Char(
        related='company_id.xunnel_token',
        help="Key-like text for authentication in controllers.",
        readonly=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self.env.company.write({
                'xunnel_token': vals.get('xunnel_token') or self.env.company.xunnel_token,
            })
            vals.pop('xunnel_token', None)
        return super().create(vals_list)

    @assert_xunnel_token
    def sync_xunnel_providers(self):
        current_company = self.company_id if self.company_id else self.env.company
        status, response = current_company._sync_xunnel_providers()
        if not status:
            error = _("An error has occurred while synchronizing your banks. %s")
            raise exceptions.UserError(error % response)
        message = _("Success! %s banks have been synchronized.") % len(response)
        action_params = {'message': message, 'message_class': 'success'}
        return {
            'type': 'ir.actions.client',
            'tag': 'account_xunnel.synchronized_accounts',
            'name': _('Xunnel response.'),
            'target': 'new',
            'params': action_params,
        }
