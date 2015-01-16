# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#
#    Copyright (c) 2011 Soluntec - Soluciones Tecnológicas
#                       (http://www.soluntec.es) All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################

from openerp import models, fields
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT
import time


class account_issued_check(models.Model):
    '''
    Account Issued Check
    '''
    _name = 'account.issued.check'
    _description = 'Manage Checks'

    number = fields.Char('Numero de Documento', required=True)
    amount = fields.Float('Cantidad del Documento', required=True)
    date_out = fields.Date('Fecha de ingreso', required=True)
    date = fields.Date('Fecha', required=True)
    debit_date = fields.Date('Fecha de Emision', readonly=True)
    date_changed = fields.Date('Fecha de Cambio', readonly=True)
    receiving_partner_id = fields.Many2one(
        'res.partner', 'Entidad Receptora', required=False, readonly=True)
    bank_id = fields.Many2one('res.bank', 'Banco', required=True)
    on_order = fields.Char('A la Orden')
    signatory = fields.Char('Firmante')
    clearing = fields.Selection(
        [('24', '24 hs'), ('48', '48 hs'), ('72', '72 hs')],
        'Tiempo Efecto', default='24')
    origin = fields.Char('Origen')
    account_bank_id = fields.Many2one('res.partner.bank', 'Cuenta Destino')
    voucher_id = fields.Many2one(
        'account.voucher', 'Comprobante', required=True)
    issued = fields.Boolean('Emitido')
    picture = fields.Binary('Image')

    _rec_name = 'number'


class account_third_check(models.Model):
    '''
    Account Third Check
    '''
    _name = 'account.third.check'
    _description = 'Manage Checks'

    number = fields.Char('Numero de Documento', required=True)
    amount = fields.Float('Cantidad de Documento', required=True)
    date_in = fields.Date('Fecha de Ingreso', required=True)
    date = fields.Date(
        'Fecha de Documento', required=True,
        default=lambda *a: time.strftime(DEFAULT_SERVER_DATE_FORMAT))
    date_out = fields.Date('Fecha de Emision', readonly=True)
    source_partner_id = fields.Many2one(
        'res.partner', 'Empresa Origen', readonly=True)
    destiny_partner_id = fields.Many2one(
        'res.partner', 'Empresa Destino', readonly=False,
        states={'delivered': [('required', True)]})
    state = fields.Selection(
        [('draft', 'Draft'),
         ('C', 'En Cartera'),
         ('deposited', 'Deposited'),
         ('delivered', 'Delivered'),
         ('rejected', 'Rejected')], 'State', required=True, default='draft')
    bank_id = fields.Many2one('res.bank', 'Banco', required=True)
    on_order = fields.Char('A la Orden')
    signatory = fields.Char('Firmante')
    clearing = fields.Selection(
        [('24', '24 hs'), ('48', '48 hs'), ('72', '72 hs')],
        'Tiempo Efecto', default='24')
    origin = fields.Char('Origen')
    account_bank_id = fields.Many2one('res.partner.bank', 'Cuenta Destino')
    voucher_id = fields.Many2one(
        'account.voucher', 'Comprobante', required=True)
    reject_debit_note = fields.Many2one(
        'account.invoice', 'Debito Por Rechazo')
    picture = fields.Binary('Image')

    _rec_name = 'number'
