# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import threading
import pooler
from datetime import datetime
import time
from osv import osv, fields

class unpaid_wizard(osv.osv_memory):
    _name = 'unpaid.wizard'
    _description = 'Set and account payment as unpaid'

    _columns = {
        'date':fields.date('Date', required=True),
        'expenses':fields.boolean('Account expenses?'),
        'expense_amount':fields.float('Expenses amount')
    }
    _defaults = {
        'date': lambda *a: time.strftime('%Y-%m-%d'),
    }

    def unpaid(self, cr, uid, ids, context=None):
        """
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        """
        if context is None:
            context = {}
        line_obj = self.pool.get('payment.line')
        assert context.get('active_model') == 'payment.line',\
             'Incorrect use of the unpaid wizard'
        company_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id.id
        data = self.browse(cr, uid, ids, context=context)[0]
        for line in line_obj.browse(cr, uid, context.get('active_ids'), context=context):

            currency_id = line.order_id.mode.journal.currency and line.order_id.mode.journal.currency.id or company_currency_id
            period_obj = period_obj = self.pool.get('account.period')
            period_ids = period_obj.find(cr, uid, data.date, context=context)
            period_id = period_ids and period_ids[0] or False
            journal_id = line.order_id.mode.journal.id
            move_id = self.pool.get('account.move').create(cr, uid, {
                'name': '/',
                'journal_id': journal_id,
                'period_id': period_id,
            }, context)

            line_amount = line.amount
            bank_account_id = line.order_id.mode.journal.default_credit_account_id.id
            unpaid_account_id = line.order_id.mode.cuenta_efectos_impagados.id
            bank_expense_account_id = line.order_id.mode.expense_account.id

            acc_cur = unpaid_account_id
            ctx = context.copy()
            ctx['res.currency.compute.account'] = acc_cur
            amount = self.pool.get('res.currency').compute(cr, uid, currency_id, company_currency_id, line_amount, ctx)

            val = {
                'name': "UNPAID - " + line.order_id.reference + "/" + line.name,
                'move_id': move_id,
                'date':  data.date,
                'ref': line.move_line_id and line.move_line_id.ref or False,
                'partner_id': line.partner_id and line.partner_id.id or False,
                'account_id': unpaid_account_id,
                'debit': amount,
                'credit':  0.0,
                'journal_id': journal_id,
                'period_id': period_id,
                'currency_id': currency_id,
            }

            #amount = self.pool.get('res.currency').compute(cr, uid, currency_id, company_currency_id, line_amount, context=ctx)
            if currency_id <> company_currency_id:
                amount_cur = self.pool.get('res.currency').compute(cr, uid, company_currency_id, currency_id, amount, context=ctx)
                val['amount_currency'] = -amount_cur

            if line.account_id and line.account_id.currency_id and line.account_id.currency_id.id <> company_currency_id:
                val['currency_id'] = line.account_id.currency_id.id
                if company_currency_id == line.account_id.currency_id.id:
                    amount_cur = line_amount
                else:
                    amount_cur = self.pool.get('res.currency').compute(cr, uid, company_currency_id, line.account_id.currency_id.id, amount, context=ctx)
                val['amount_currency'] = amount_cur

            unpaid_line_id = self.pool.get('account.move.line').create(cr, uid, val, context, check=False)
            if currency_id <> company_currency_id:
                amount_currency = line_amount
                move_currency_id = currency_id
            else:
                amount_currency = False
                move_currency_id = False

            if data.expenses:

                val = {
                    'name': "EXP UNPAID - " + line.order_id.reference + "/" + line.name,
                    'move_id': move_id,
                    'date':  data.date,
                    'ref': line.move_line_id and line.move_line_id.ref or False,
                    'partner_id':  False,
                    'account_id': bank_expense_account_id,
                    'debit': data.expense_amount,
                    'credit':  0.0,
                    'journal_id': journal_id,
                    'period_id': period_id,
                    'currency_id': currency_id,
                }
                expense_line_id = self.pool.get('account.move.line').create(cr, uid, val, context, check=False)

                amount_bank = amount + data.expense_amount
            else:
                amount_bank = amount

            val = {
                'name': " UNPAID - " + line.order_id.reference + "/" + line.name,
                'move_id': move_id,
                'date':  data.date,
                'ref': line.move_line_id and line.move_line_id.ref or False,
                'partner_id':  False,
                'account_id': bank_account_id,
                'debit': 0.0,
                'credit':  amount_bank,
                'journal_id': journal_id,
                'period_id': period_id,
                'currency_id': currency_id,
            }
            bank_line_id = self.pool.get('account.move.line').create(cr, uid, val, context)

            aml_ids = [x.id for x in self.pool.get('account.move').browse(cr, uid, move_id, context).line_id]
            for x in self.pool.get('account.move.line').browse(cr, uid, aml_ids, context):
                if x.state != 'valid':
                    raise osv.except_osv(_('Error !'), _('Account move line "%s" is not valid') % x.name)
            self.pool.get('payment.line').write(cr, uid, [line.id], {
                'unpaid_move_id': unpaid_line_id
            },
            context)

        return {'type': 'ir.actions.act_window_close'}
