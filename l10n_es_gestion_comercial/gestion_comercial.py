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

from openerp import models, fields, _, api
from datetime import datetime
# from osv import fields, osv
# import netsvc
# from tools import config
import time
from openerp import pooler


#
# Diarios
#
# =============================================================================
# =========================== INHERIT CLASS ACCOUNT JOURNAL ===================
# =============================================================================
# Se modifica la clase de diarios contables para añadir nuevos campos que
# serán luego utilizados para determinar el comportamiento de los comprobantes
# de pago
class account_journal(models.Model):
    # Se añaden a los comprobantes de pago, los campos de cheque recibido y de
    # pago indirecto. El campo de pago indirecto es un campo no visible, que
    # se utilizará para registrar aquellos pagos que corresponden a documentos
    # bancarios, es decir que no abonan directamente la factura sino que
    # agrupan la deuda en un nuevo efecto cobrable

    _inherit = 'account.journal'
    _name = 'account.journal'

    indirect_payment = fields.Boolean(
        u'Gestión de efectos comerciales',
        help="Marcar si se va a utilizar este diario para registrar apuntes "
        "de efectos correspondiente a gestión comercial (pagarés, giros, "
        "cheques, etc). El sistema usuará la cuenta definida en la ficha "
        "de cliente. Si está en blanco usuará la definida en este diario")
    without_account_efect = fields.Boolean(
        'Sin efecto contable', help="Si se marca esta opción, el sistema "
        "usará la cuenta de cobrables/pagables del cliente en lugar de la "
        "cuenta de fectos definidas en el diario o cliente")
    indirect_payment_type = fields.Selection(
        [('documento', 'Documento de Cobro'),
         ('impago', 'Impagos'),
         ('incobrable', 'Incobrable')],
        'Tipo de Efecto Comercial', select=True)
    gestion_cobro = fields.Boolean(
        u'Gestión de cobro', help="Marque esta opción si el diario será "
        "utilizado para operaciones de gestión de cobro")
    descuento_efectos = fields.Boolean(
        'Descuento de Efectos', help="Marque esta opción si el diario será "
        "utilizado para operaciones de- descuento de efectos")
    property_account_descuento_efectos = fields.Many2one(
        'account.account', "Cuenta de descuento de Efectos",
        company_dependent=True)


#
# Partners
#
# =============================================================================
# =========================== INHERIT CLASS RES_PARTNER =======================
# =============================================================================
# Se añade campos a los partners para registrar las cuentas a utilizar
# para efectos comerciales
class res_partner(models.Model):

    _inherit = 'res.partner'
    _name = 'res.partner'

    property_account_efectos_cartera = fields.Many2one(
        'account.account', "Efectos Comerciales en Cartera",
        domain="[('type', '=', 'receivable')]",
        help="Esta cuenta será utilizada en lugar de la cuenta por defecto "
        "del diario para registrar los efectos comerciales en cartera",
        company_dependent=True)
    property_account_impagos = fields.Many2one(
        'account.account', "Impagos",
        domain="[('type', '=', 'receivable')]",
        help="Esta cuenta será utilizada en lugar de la cuenta por defecto "
        "del diario para registrar los efectos impagados",
        company_dependent=True)
    property_account_efectos_incobrables = fields.Many2one(
        'account.account', "Incobrables",
        domain="[('type', '=', 'other')]",
        help="Esta cuenta será utilizada en lugar de la cuenta por defecto "
        "para registrar los efectos incobrables",
        company_dependent=True)
    property_account_efectos_descontados = fields.Many2one(
        'account.account', "Efectos Descontados",
        domain="[('type', '=', 'other')]",
        help="Cuenta para efectos descontados",
        company_dependent=True)


#
# Comprobantes de Pago
#
# =============================================================================
# ============================ INHERIT CLASS ACCOUNT VOUCHER ==================
# =============================================================================
# Se modifica la gestión de comprobantes de pago para que amplie la
# funcionalidad para registrar pagos mediante pagarés,cheques, etc..
class account_voucher(models.Model):
    # Se añaden a los comprobantes de pago, los campos de cheque recibido y de
    # pago indirecto. El campo de pago indirecto es un campo no visible, que
    # se utilizará para registrar aquellos pagos que corresponden a documentos
    # bancarios, es decir que no abonan directamente la factura sino que
    # agrupan la deuda en un nuevo efecto cobrable
    _inherit = 'account.voucher'
    _name = 'account.voucher'

    # ================= METHODS ================= #
    def onchange_partner_id(self, cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, context=None):

        # We call the original event to give us back the original values
        res = super(account_voucher, self).onchange_partner_id(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, context)

        if journal_id:
            journal_pool = self.pool.get('account.journal')
            journal = journal_pool.browse(cr, uid, journal_id, context=context)

            if journal.indirect_payment:
                res['value']['indirect_payment'] = True
            else:
                res['value']['indirect_payment'] = False

        return res

    def first_move_line_get(self, cr, uid, voucher_id, move_id, company_currency, current_currency, context=None):
        '''
        Return a dict to be use to create the first account move line of given voucher.

        :param voucher_id: Id of voucher what we are creating account_move.
        :param move_id: Id of account move where this line will be added.
        :param company_currency: id of currency of the company to which the voucher belong
        :param current_currency: id of currency of the voucher
        :return: mapping between fieldname and value of account move line to create
        :rtype: dict
        '''
        move_line_vals = super(account_voucher, self).first_move_line_get(cr, uid, voucher_id, move_id, company_currency, current_currency, context=context)
        voucher_brw = self.pool.get('account.voucher').browse(cr,uid,voucher_id,context)
        cuenta_id = False

        if voucher_brw.journal_id.indirect_payment:
            if voucher_brw.journal_id.without_account_efect:
                cuenta_id = voucher_brw.partner_id.property_account_receivable.id,
            else:
                if voucher_brw.journal_id.indirect_payment_type == "documento":
                    if voucher_brw.partner_id.property_account_efectos_cartera.id:
                        cuenta_id = voucher_brw.partner_id.property_account_efectos_cartera.id
                    else:
                        cuenta_id = voucher_brw.account_id.id
                elif voucher_brw.journal_id.indirect_payment_type == "impago":
                    if voucher_brw.partner_id.property_account_impagos.id:
                        cuenta_id = voucher_brw.partner_id.property_account_impagos.id
                    else:
                        cuenta_id = voucher_brw.account_id.id
                elif voucher_brw.journal_id.indirect_payment_type == "incobrable":
                    if voucher_brw.partner_id.property_account_efectos_incobrables.id:
                        cuenta_id = voucher_brw.partner_id.property_account_efectos_incobrables.id
                    else:
                        cuenta_id = voucher_brw.account_id.id
        else:
            cuenta_id = voucher_brw.account_id.id
        move_line_vals['account_id'] = cuenta_id

        return move_line_vals

    # ================= FIELDS ================= #
    payment_type = fields.Many2one(
        'payment.mode.type', 'Tipo de Pago',
        help="Tipo de pago establecido para el nuevo efecto a crear")
    received_check = fields.Boolean(
        'Received check', help="To write down that a check in paper "
        "support has been received, for example.")
    indirect_payment = fields.Boolean(
        'Document check', help="To mark if is not a direct payment")
    expenses = fields.Boolean(
        'Expenses', help="To mark if you have to take into account expenses")
    issued_check_ids = fields.One2many(
        'account.issued.check', 'voucher_id', 'Cheques emitidos')
    third_check_receipt_ids = fields.One2many(
        'account.third.check', 'voucher_id', 'Cheques de Terceros')
    third_check_ids = fields.Many2many(
        'account.third.check', 'third_check_voucher_rel',
        'third_check_id', 'voucher_id', 'Cheques de Terceros')
    property_account_gastos = fields.Many2one(
        'account.account', "Cuenta Gastos",
        domain="[('type', '=', 'other')]",
        help="Gastos ocasionados por el impago",
        company_dependent=True)
    expense_amount = fields.Float('Cantidad Gastos')
    invoice_expense = fields.Boolean('Contabilizar Gastos')


#
# Apuntes contables
#
# =============================================================================
# =========================== INHERIT CLASS ACCOUNT VOUCHER ===================
# =============================================================================
# Se realizan los siguientes cambios....
# Se sobreescribe el campo funcional de tipo de pago con una nueva versión que
# hace lo mismo pero buscando ademas el valor del comprante de pago si el
# efecto no esta relacionado directamente con una factura
class account_move_line(models.Model):
    _name = 'account.move.line'
    _inherit = 'account.move.line'

# Se amplia el metodo original de account_payment_extension.
# Ahora si no encuentra el tipo de pago en la factura asociada el apunte,
# lo busca en el comprobante de pago... Si no esta en ninguno de los dos,
# lo deja en blanco.
    def _payment_type_get(self, cr, uid, ids, field_name, arg, context={}):
        result = {}
        invoice_obj = self.pool.get('account.invoice')
        voucher_obj = self.pool.get('account.voucher')
        for rec in self.browse(cr, uid, ids, context):
            result[rec.id] = False
            invoice_id = invoice_obj.search(cr, uid, [('move_id', '=', rec.move_id.id)], context=context)
            if invoice_id:
                inv = invoice_obj.browse(cr, uid, invoice_id[0], context)
                if inv.payment_type:
                    result[rec.id] = inv.payment_type.id
            else:
                voucher_id = voucher_obj.search(cr, uid, [('move_id', '=', rec.move_id.id)], context=context)
                if voucher_id:
                    voucher = voucher_obj.browse(cr, uid, voucher_id[0], context)
                    if voucher.payment_type:
                        result[rec.id] = voucher.payment_type.id
                    else:
                        result[rec.id] = False
                else:
                    result[rec.id] = False
        return result

# Se crea un nuevo campo funcional de tipo booleano que obtiene si es pago
# corresponde a un efecto de gestión comercial o no.
    @api.multi
    def _indirect_payment_get(self):
        for rec in self:
            voucher = self.env['account.voucher'].search(
                [('move_id', '=', rec.move_id.id)])
            rec.indirect_payment = False
            if voucher:
                if voucher.indirect_payment:
                    if rec.debit > 0:  # rec.id.account_id.type = 'receivable'
                        rec.indirect_payment = True


# Creamos los metodos de busqueda para obtener los registros que tienen
# el check de efecto de gestión comercial marcado
    def _indirect_payment_search(self, cr, uid, obj, name, args, context={}):
        """ Definition for searching account move lines with indirect_payment check ('indirect_payment','=',True)"""
        for x in args:
            if (x[2] is True) and (x[1] == '=') and (x[0] == 'indirect_payment'):
                cr.execute('SELECT l.id FROM account_move_line l ' \
                    'LEFT JOIN account_voucher i ON l.move_id = i.move_id ' \
                    'WHERE i.indirect_payment = TRUE AND l.debit > 0', []) # NOTA A MEJORAR CUANDO DEBAN INCLUIRSE LOS EFECTOS DE PAGO
                res = cr.fetchall()
                if not len(res):
                    return [('id', '=', '0')]
            elif (x[2] is False) and (x[1] == '=') and (x[0] == 'indirect_payment'):
                cr.execute('SELECT l.id FROM account_move_line l ' \
                    'LEFT JOIN account_voucher i ON l.move_id = i.move_id ' \
                    'WHERE i.indirect_payment is null or i.indirect_payment = False', [])
                res = cr.fetchall()
                if not len(res):
                    return [('id', '=', '0')]
        return [('id', 'in', [x[0] for x in res])]

    def _get_move_lines_invoice(self, cr, uid, ids, context=None):
        result = set()
        invoice_obj = self.pool['account.invoice']
        for invoice in invoice_obj.browse(cr, uid, ids, context=context):
            if invoice.move_id:
                result.add(invoice.move_id.id)
        return list(result)

#     payment_type = fields.Many2one('payment.type', "Payment type", compute=_payment_type_get)
#     store={
#            'account.move.line': (lambda self, cr, uid, ids, context=None:
#                                  ids, None, 10),
#            'account.invoice': (_get_move_lines_invoice,
#                                ['payment_type'], 20),
#        }
    indirect_payment = fields.Boolean(
        "Indirect Payment",
        compute=_indirect_payment_get,
        fnct_search=_indirect_payment_search)
    payment_order_check = fields.Boolean("Mostrar en Efectos")
    to_concile_account = fields.Many2one(
        'account.account', 'Expected Account To Concile',
        help='Cuenta con la que deberá ser conciliada en un apunte posterior')


#
# Modo de Pago
#
# ===========================================================================
# ========================== INHERIT CLASS PAYMENT_MODE =====================
# ===========================================================================
# Se añaden campos a los modos de pago para poder gestionar los descuentos de
# efectos
class payment_mode(models.Model):
    _inherit = 'payment.mode'

    cuenta_deuda_efectos_descontados = fields.Many2one(
        'account.account', 'Cuenta Deuda Efectos Descontados',
        help='Cuenta para efectos descontados. Ejemplo: 5208xx')
    cuenta_factoring = fields.Many2one(
        'account.account', 'Cuenta Deudas por Operaciones de Factoring',
        help='Cuenta para deudas por operaciones de Factoring. Ejemplo: 5209xx')
    cuenta_efectos_descontados = fields.Many2one(
        'account.account', u'Cuenta Genérica Efectos Descontados',
        help='Cuenta para efectos descontados. Ejemplo: 4311x')
    cuenta_efectos_impagados = fields.Many2one(
        'account.account', u'Cuenta Genérica Efectos Impagados',
        help='Cuenta para efectos impagados. Ejemplo: 4315x')
    value_amount = fields.Float(u'% Interés', help="% de gastos sobre cobro")
    value_amount_unpaid = fields.Float(
        u'% Interés impago', help="% de gastos sobre cobro")
    expense_account = fields.Many2one(
        'account.account', 'Cuenta Gastos',
        help='Cuenta para gastos de cobro')


#
# Orden de Cobro
#
# ==================================================================================
# ============================== INHERIT CLASS PAYMENT_ORDER========================
# ==================================================================================
# Se amplia la funcuonalidad de las ordenes de cobro para registrar descuentos de efectos
class payment_line(models.Model):
    _name = 'payment.line'
    _inherit = 'payment.line'

    def _state_get(self, cr, uid, ids, field_name, arg, context=None):
        result = {}
        move_line_obj = self.pool.get('account.move.line')
        for line in self.browse(cr, uid, ids, context):
            result[line.id] = 'Pending'
            if line.disccount_move_id.reconcile_id:
                result[line.id] = 'Paid'
            if line.unpaid_move_id:
                result[line.id] = 'Unpaid'
        return result

    unpaid = fields.Boolean('Unpaid')
#     state_flow = fields.Char("State", compute=_state_get)
    disccount_move_id = fields.Many2one(
        'account.move.line', 'Movimiento de efecto descontado',
        help='Movimiento del efecto descontado')
    unpaid_move_id = fields.Many2one(
        'account.move.line', 'Movimiento de efecto impagado',
        help='Movimiento del efecto impagado')

    def check_paid (self, cr, uid, automatic=False, use_new_cursor=False, context=None):
        ''' Runs through scheduler.
        @param use_new_cursor: False or the dbname
        '''
        self._check_maturity(cr, uid, use_new_cursor=use_new_cursor, context=context)

    def _check_maturity(self, cr, uid, ids=None, use_new_cursor=False, context=None):
        '''
        Call the scheduler to check the maturity of payment lines

        @param self: The object pointer
        @param cr: The current row, from the database cursor,
        @param uid: The current user ID for security checks
        @param ids: List of selected IDs
        @param use_new_cursor: False or the dbname
        @param context: A standard dictionary for contextual values
        @return:  Dictionary of values
        '''
        if context is None:
            context = {}

        try:
            if use_new_cursor:
                cr = pooler.get_db(use_new_cursor).cursor()

            company_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id.id
            payment_line_obj = self.pool.get('payment.line')
            if not ids:
                #TODO  . Mejorar rendimiento sin el bucle
                ids = payment_line_obj.search(cr, uid, [('ml_maturity_date','<=',datetime.today()),('type', '=', 'receivable')])
            for line in payment_line_obj.browse(cr,uid,ids):
                if line.disccount_move_id and not line.disccount_move_id.reconcile_id:
                    #Contabilizar el pago del efecto

                    #Se crea el asiento
                    period_obj = period_obj = self.pool.get('account.period')
                    period_ids = period_obj.find(cr, uid, datetime.today(), context=context)
                    period_id = period_ids and period_ids[0] or False

                    currency_id = line.order_id.mode.journal.currency and line.order_id.mode.journal.currency.id or company_currency_id

                    move_id = self.pool.get('account.move').create(cr, uid, {
                        'name': line.disccount_move_id and line.disccount_move_id.invoice and line.disccount_move_id.invoice.name or "/",
                        'journal_id': line.order_id.mode.journal.id,
                        'period_id': period_id,
                    }, context)

                    # Se crea el apunte  para la cuenta de efectos en gestión de cobros
                    val = {
                        'name': line.disccount_move_id and line.disccount_move_id.name + '- paid' or '/',
                        'move_id': move_id,
                        'date': line.ml_maturity_date or datetime.today(),
                        'ref': line.disccount_move_id and line.disccount_move_id.ref or False,
                        'partner_id': line.partner_id and line.partner_id.id or False,
                        'account_id': line.disccount_move_id.account_id.id,
                        'debit': 0.0,
                        'credit': line.disccount_move_id.debit,
                        'journal_id': line.order_id.mode.journal.id,
                        'period_id': period_id,
                        'currency_id': currency_id,
                    }

                    partner_line_id = self.pool.get('account.move.line').create(cr, uid, val, context, check=False)

                   # Se crea ahora el apunte para la deuda por efectos descontados
                    if (line.order_id.create_account_moves == 'descuento-efecto'):
                        cuenta_deuda_descuento_efectos = line.order_id.mode.cuenta_deuda_efectos_descontados.id   #5208
                    if (line.order_id.create_account_moves == 'factoring'):
                        cuenta_deuda_descuento_efectos = line.order_id.mode.cuenta_factoring.id

                    val_ef_descontados = {
                          'name': line.disccount_move_id and line.disccount_move_id.name + '/ PAID' or '/',
                          'move_id': move_id,
                          'date': line.ml_maturity_date or datetime.today(),
                          'ref': line.disccount_move_id and line.disccount_move_id.ref or False,
                          'partner_id': False,
                          'account_id': cuenta_deuda_descuento_efectos,
                          'debit': line.disccount_move_id.debit,
                          'credit': 0.0,
                          'journal_id': line.order_id.mode.journal.id,
                          'period_id': period_id,
                          'currency_id': currency_id,
                    }

                    partner_line_id_efectos_descontados = self.pool.get('account.move.line').create(cr, uid, val_ef_descontados, context)

                    # Comprobamos asientos
                    aml_ids = [x.id for x in self.pool.get('account.move').browse(cr, uid, move_id, context).line_id]
                    for x in self.pool.get('account.move.line').browse(cr, uid, aml_ids, context):
                        if x.state <> 'valid':
                            raise osv.except_osv(_('Error !'), _('Account move line "%s" is not valid') % x.name)

                    # Preparamos la conciliación

                    lines_to_reconcile = [
                        partner_line_id,
                        line.disccount_move_id.id
                    ]
                    amount = 0
                    for rline in self.pool.get('account.move.line').browse(cr, uid, lines_to_reconcile, context):
                        amount += rline.debit - rline.credit

                    currency = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id

                    if self.pool.get('res.currency').is_zero(cr, uid, currency, amount):
                       self.pool.get('account.move.line').reconcile(cr, uid, lines_to_reconcile, 'payment', context=context)
                    else:
                       self.pool.get('account.move.line').reconcile_partial(cr, uid, lines_to_reconcile, 'payment', context)

                    # Cambia la información del estado
                    #payment_line_obj.write (cr, uid, line.id, {'state_flow':'Paid'})

            if use_new_cursor:
                cr.commit()
        finally:
            if use_new_cursor:
                try:
                    cr.close()
                except Exception:
                    pass
        return {}


class payment_order(models.Model):
    _name = 'payment.order'
    _inherit = 'payment.order'

    create_account_moves = fields.Selection(
        [('bank-statement', 'Bank Statement'),
         ('direct-payment', 'Direct Payment'),
         ('factoring', 'Factoring'),
         ('descuento-efecto', 'Descuento de Efectos')],
        'Create Account Moves', required=True,
        states={'done': [('readonly', True)]},
        help="Indicates when account moves should be created for order "
        "payment lines. \"Bank Statement\" will wait until user introduces "
        "those payments in bank a bank statement. \"Direct Payment\" will "
        "mark all payment lines as payied once the order is done.")
    expense_moves = fields.Boolean('Contabilizar Gastos')
    expenses = fields.Float('Gastos remesa', help="Gastos de remesa")
    due_date = fields.Date('Fecha Vencimiento')

    def accounting_factoring(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        self.write(cr, uid, ids, {'date_done': time.strftime('%Y-%m-%d')})
        company_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id.id

        for order in self.browse(cr, uid, ids, context):
            currency_id = order.mode.journal.currency and order.mode.journal.currency.id or company_currency_id
            if ((order.create_account_moves != 'factoring') and (order.create_account_moves != 'descuento-efecto')):
                continue
            amount_tot = 0
            for line in order.line_ids:
                if not line.amount:
                    continue

                if not line.account_id:
                    raise osv.except_osv(_('Error!'), _('Payment order should create account moves but line with amount %(amount).2f for partner "%(partner)s" has no account assigned.') % {'amount': line.amount, 'partner': line.partner_id.name} )

                move_id = self.pool.get('account.move').create(cr, uid, {
                    'name': '/',
                    'ref': order.reference,
                    'journal_id': order.mode.journal.id,
                    'period_id': order.period_id.id,
                }, context)

                if line.type == 'payable':
                    line_amount = line.amount_currency or line.amount
                else:
                    line_amount = -line.amount_currency or -line.amount

                acc_cur = ((line_amount<=0) and order.mode.journal.default_debit_account_id) or line.account_id

                ctx = context.copy()
                ctx['res.currency.compute.account'] = acc_cur
                amount = self.pool.get('res.currency').compute(cr, uid, currency_id, company_currency_id, line_amount, ctx)
                amount_tot = amount_tot +  amount

                val = {
                    'name': line.move_line_id and line.move_line_id.name or '/',
                    'move_id': move_id,
                    'date': order.date_done,
                    'ref': order.reference + "/" + line.name,
                    'partner_id': line.partner_id and line.partner_id.id or False,
                    'account_id': line.account_id.id,
                    'debit': ((amount>0) and amount) or 0.0,
                    'credit': ((amount<0) and -amount) or 0.0,
                    'journal_id': order.mode.journal.id,
                    'period_id': order.period_id.id,
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

                partner_line_id = self.pool.get('account.move.line').create(cr, uid, val, context, check=False)

                # Fill the secondary amount/currency
                # if currency is not the same than the company
                if currency_id <> company_currency_id:
                    amount_currency = line_amount
                    move_currency_id = currency_id
                else:
                    amount_currency = False
                    move_currency_id = False

                if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                    if order.create_account_moves == 'factoring':
                        name = unicode('Factoring /') + order.mode.journal.name
                    if order.create_account_moves == 'descuento-efecto':
                        name = unicode('Desc. de efectos /') + order.mode.journal.name
                    #Si el cliente tiene informada la cuenta de efectos descontados usamos esa.. si no usamos la del modo de pago
                    if line.partner_id.property_account_efectos_descontados:
                        cuenta_descuento_efectos = line.partner_id.property_account_efectos_descontados.id,
                    else:
                        cuenta_descuento_efectos = order.mode.cuenta_factoring.id,


                    move_line_efecto_id = self.pool.get('account.move.line').create(cr, uid, {
                        'name': name or '/',
                        'move_id': move_id,
                        'date': order.date_done,
                        'ref': order.reference + "/" + line.name,
                        'partner_id': line.partner_id and line.partner_id.id or False,
                        'account_id': cuenta_descuento_efectos[0],
                        'debit': ((amount < 0) and -amount) or 0.0,
                        'credit': ((amount > 0) and amount) or 0.0,
                        'journal_id': order.mode.journal.id,
                        'period_id': order.period_id.id,
                        'amount_currency': amount_currency,
                        'currency_id': move_currency_id,
                        'date_maturity': order.due_date,
                        'payment_order_check': True,
                    }, context)

                    self.pool.get('payment.line').write(cr, uid, [line.id], {
                        'disccount_move_id': move_line_efecto_id,
                    }, context)

                    if order.create_account_moves == 'factoring':
                        ref = unicode('Factoring /') + order.mode.journal.name
                    if order.create_account_moves == 'descuento-efecto':
                        ref = unicode('Desc. de efectos /') + order.mode.journal.name



                aml_ids = [x.id for x in self.pool.get('account.move').browse(cr, uid, move_id, context).line_id]
                for x in self.pool.get('account.move.line').browse(cr, uid, aml_ids, context):
                    if x.state <> 'valid':
                        raise osv.except_osv(_('Error !'), _('Account move line "%s" is not valid') % x.name)
                    #self.pool.get('account.move.line').write(cr, uid, [x.id], {'ref':ref})

                if line.move_line_id and not line.move_line_id.reconcile_id:
                    # If payment line has a related move line, we try to reconcile it with the move we just created.
                    lines_to_reconcile = [
                        partner_line_id,
                    ]

                    # Check if payment line move is already partially reconciled and use those moves in that case.
                    if line.move_line_id.reconcile_partial_id:
                        for rline in line.move_line_id.reconcile_partial_id.line_partial_ids:
                            lines_to_reconcile.append( rline.id )
                    else:
                        lines_to_reconcile.append( line.move_line_id.id )

                    amount = 0.0
                    for rline in self.pool.get('account.move.line').browse(cr, uid, lines_to_reconcile, context):
                        amount += rline.debit - rline.credit

                    currency = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id

                    if self.pool.get('res.currency').is_zero(cr, uid, currency, amount):
                        self.pool.get('account.move.line').reconcile(cr, uid, lines_to_reconcile, 'payment', context=context)
                    else:
                        self.pool.get('account.move.line').reconcile_partial(cr, uid, lines_to_reconcile, 'payment', context)

                if order.mode.journal.entry_posted:
                    self.pool.get('account.move').write(cr, uid, [move_id], {
                        'state':'posted',
                    }, context)

                self.pool.get('payment.line').write(cr, uid, [line.id], {
                    'payment_move_id': move_id,
                }, context)

            ##########################################################################################
            # Genera el movimiento total de la remesa para la deuda, el ingreso y los gastos bancarios

            ## Creamos el apunte de descuento de efectos o factoring

            move_tot_id = self.pool.get('account.move').create(cr, uid, {
                'name': order.reference or '/',
                'ref': order.reference,
                'journal_id': order.mode.journal.id,
                'period_id': order.period_id.id,
            }, context)
            amount_tot_cur = 0
            if currency_id <> company_currency_id:
                amount_tot_cur = self.pool.get('res.currency').compute(cr, uid, company_currency_id, currency_id, amount_tot, context=ctx)
                val['amount_tot_currency'] = -amount_tot_cur

            if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                if (order.create_account_moves == 'descuento-efecto'):
                    cuenta_deuda_descuento_efectos = order.mode.cuenta_deuda_efectos_descontados.id   #5208
                if (order.create_account_moves == 'factoring'):
                    cuenta_deuda_descuento_efectos = order.mode.cuenta_factoring.id

                if amount_tot >= 0:
                    account_id = order.mode.journal.default_credit_account_id.id  #572
                else:
                    account_id = order.mode.journal.default_debit_account_id.id

                val_ef_descontados = {
                      'name': 'Deuda descuento efectos',
                      'move_id': move_tot_id,
                      'date': order.date_done,
                      'ref': order.reference + "/" + line.name or False,
                      'partner_id': False,
                      'account_id': cuenta_deuda_descuento_efectos,
                      'debit': ((amount_tot>0) and amount_tot) or 0.0,
                      'credit': ((amount_tot<0) and -amount_tot) or 0.0,
                      'journal_id': order.mode.journal.id,
                      'period_id': order.period_id.id,
                      'currency_id': currency_id,
                }

                partner_line_id_efectos_descontados = self.pool.get('account.move.line').create(cr, uid, val_ef_descontados, context, check=False)


            if order.expense_moves:
                self.pool.get('account.move.line').create(cr, uid, {
                    'name': 'Ingreso descuento',
                    'move_id': move_tot_id,
                    'date': order.date_done,
                    'ref': order.reference + "/" + line.name or '/' or False,
                    'partner_id': False,
                    'account_id': account_id,
                    'debit': ((amount_tot < 0) and -(amount_tot + order.expenses)) or 0.0,
                    'credit': ((amount_tot > 0) and (amount_tot - order.expenses)) or 0.0,
                    'journal_id': order.mode.journal.id,
                    'period_id': order.period_id.id,
                    'amount_currency': (amount_tot_cur-(amount_tot_cur*(order.mode.value_amount/100))),
                    'currency_id': currency_id,
                }, context)

                self.pool.get('account.move.line').create(cr, uid, {
                    'name': 'Gastos descuento',
                    'move_id': move_tot_id,
                    'date': order.date_done,
                    'ref': order.reference + "/" + line.name,
                    'partner_id': False,
                    'account_id': order.mode.expense_account.id,
                    'debit': ((amount_tot < 0) and order.expenses) or 0.0,
                    'credit': ((amount_tot > 0) and order.expenses) or 0.0,
                    'journal_id': order.mode.journal.id,
                    'period_id': order.period_id.id,
                    'amount_currency': ((amount_tot_cur *(order.mode.value_amount/100))),
                    'currency_id': currency_id,
                }, context)
            else:
                self.pool.get('account.move.line').create(cr, uid, {
                    'name': 'Ingreso descuento',
                    'move_id': move_tot_id,
                    'date': order.date_done,
                    'ref': order.reference + "/" + line.name,
                    'partner_id': False,
                    'account_id': account_id,
                    'debit': ((amount_tot < 0) and -amount_tot) or 0.0,
                    'credit': ((amount_tot > 0) and amount_tot) or 0.0,
                    'journal_id': order.mode.journal.id,
                    'period_id': order.period_id.id,
                    'amount_currency': amount_currency,
                    'currency_id': currency_id,
                }, context)




            if order.mode.journal.entry_posted:
                self.pool.get('account.move').write(cr, uid, [move_tot_id], {
                    'state':'posted',
                }, context)


        return True

    def action_pending(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        #self.accounting_1 (cr, uid, ids, context)

    def set_done(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        for order in self.pool.get('payment.order').browse (cr, uid, ids):
            if order.create_account_moves != 'direct-payment':
                self.accounting_factoring(cr, uid, [order.id])
                wf_service = netsvc.LocalService("workflow")
                self.write(cr, uid, order.id, {'date_done': time.strftime('%Y-%m-%d')})
                wf_service.trg_validate(uid, 'payment.order', order.id, 'done', cr)
            else:
                result = super(payment_order, self).set_done(cr, uid,[order.id], context)

    def set_finish(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        wf_service = netsvc.LocalService("workflow")
        wf_service.trg_validate(uid, 'payment.order', ids[0], 'finish', cr)

        company_currency_id = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id.id

        for order in self.browse(cr, uid, ids, context):
            if (order.create_account_moves != 'descuento-efecto'):
                continue

            for line in order.line_ids:
                if not line.amount:
                    continue

                if not line.account_id:
                    raise osv.except_osv(_('Error!'), _('Payment order should create account moves but line with amount %(amount).2f for partner "%(partner)s" has no account assigned.') % {'amount': line.amount, 'partner': line.partner_id.name} )

                move_id = self.pool.get('account.move').create(cr, uid, {
                    'name': '/',
                    'journal_id': order.mode.journal.id,
                    'period_id': order.period_id.id,
                }, context)

                currency_id = order.mode.journal.currency and order.mode.journal.currency.id or company_currency_id

                if line.type == 'payable':
                    line_amount = line.amount_currency or line.amount
                else:
                    line_amount = -line.amount_currency or -line.amount

                if line_amount >= 0:
                    account_id = order.mode.journal.default_credit_account_id.id
                else:
                    account_id = order.mode.journal.default_debit_account_id.id
                acc_cur = ((line_amount<=0) and order.mode.journal.default_debit_account_id) or line.account_id

                ctx = context.copy()
                ctx['res.currency.compute.account'] = acc_cur
                amount = self.pool.get('res.currency').compute(cr, uid, currency_id, company_currency_id, line_amount, context=ctx)
                if line.unpaid == False:
                    ## Creamos el apunte de PAGO descuento de efectos o factoring
                    if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                        if (order.create_account_moves == 'descuento-efecto'):
                            cuenta_deuda_descuento_efectos = order.mode.cuenta_deuda_efectos_descontados.id  #5208
                        if (order.create_account_moves == 'factoring'):
                            cuenta_deuda_descuento_efectos = order.mode.cuenta_factoring.id
                        val_ef_descontados = {
                               'name': line.move_line_id and line.move_line_id.name or '/',
                               'move_id': move_id,
                               'date': order.date_done,   ## a revisar TODO!!!!
                               'ref': order.reference,
                               'partner_id': line.partner_id and line.partner_id.id or False,
                               'account_id': cuenta_deuda_descuento_efectos,
                               'debit': ((amount<0) and -amount) or 0.0,
                               'credit': ((amount>0) and amount) or 0.0,
                               'journal_id': order.mode.journal.id,
                               'period_id': order.period_id.id,
                               'currency_id': currency_id,
                        }
                        partner_line_id_efectos_descontados = self.pool.get('account.move.line').create(cr, uid, val_ef_descontados, context, check=False)

                # Fill the secondary amount/currency
                # if currency is not the same than the company
                    if currency_id <> company_currency_id:
                        amount_currency = line_amount
                        move_currency_id = currency_id
                    else:
                        amount_currency = False
                        move_currency_id = False

                    ## Creamos el apunte de descuento de efectos
                    ref = ""
                    if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                        #Si el cliente tiene informada la cuenta de efectos descontados usamos esa.. si no usamos la del modo de pago

                        if order.create_account_moves == 'factoring':
                            name = unicode('Factoring /') + order.mode.journal.name
                        if order.create_account_moves == 'descuento-efecto':
                            name = unicode('Desc. de efectos /') + order.mode.journal.name

                        if line.partner_id.property_account_efectos_descontados:
                            cuenta_descuento_efectos = line.partner_id.property_account_efectos_descontados.id,
                        else:
                            cuenta_descuento_efectos = order.mode.cuenta_efectos_descontados.id,
                        partner_discount_line_id = self.pool.get('account.move.line').create(cr, uid, {
                            'name': name,
                            'move_id': move_id,
                            'date': order.date_done,
                            'ref': order.reference,
                            'partner_id': line.partner_id and line.partner_id.id or False,
                            'account_id': cuenta_descuento_efectos[0],
                            'debit': ((amount > 0) and amount) or 0.0,
                            'credit': ((amount < 0) and -amount) or 0.0,
                            'journal_id': order.mode.journal.id,
                            'period_id': order.period_id.id,
                            'amount_currency': amount_currency,
                            'currency_id': move_currency_id,
                            'date_maturity': order.due_date,
                            'payment_order_check': True,
                            'to_concile_account': cuenta_deuda_descuento_efectos,
                        }, context)

                    aml_ids = [x.id for x in self.pool.get('account.move').browse(cr, uid, move_id, context).line_id]
                    for x in self.pool.get('account.move.line').browse(cr, uid, aml_ids, context):
                        if x.state != 'valid':
                            raise osv.except_osv(_('Error !'), _('Account move line "%s" is not valid') % x.name)
                        #self.pool.get('account.move.line').write(cr, uid, [x.id], {'ref':ref})

                else:   # if it is an unpaid movement
                    ## Creamos el apunte de IMPAGO descuento de efectos o factoring
                    if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):

                        if line.partner_id.property_account_efectos_descontados:
                            cuenta_efectos_impagados = line.partner_id.property_account_efectos_impagados.id
                        else:
                            cuenta_efectos_impagados = order.mode.cuenta_efectos_impagados.id

                        val_ef_impagados = {
                               'name': line.move_line_id and line.move_line_id.name or '/',
                               'move_id': move_id,
                               'date': order.due_date,   ## a revisar TODO!!!!
                               'ref': order.reference,
                               'partner_id': line.partner_id and line.partner_id.id or False,
                               'account_id': cuenta_efectos_impagados,
                               'debit': ((amount<0) and -amount) or 0.0,
                               'credit': ((amount>0) and amount) or 0.0,
                               'journal_id': order.mode.journal.id,
                               'period_id': order.period_id.id,
                               'currency_id': currency_id,
                        }
                        partner_line_id_efectos_impagados = self.pool.get('account.move.line').create(cr, uid, val_ef_impagados, context, check=False)

                # Fill the secondary amount/currency
                # if currency is not the same than the company
                    if currency_id <> company_currency_id:
                        amount_currency = line_amount
                        move_currency_id = currency_id
                    else:
                        amount_currency = False
                        move_currency_id = False

                    ## Creamos el apunte de descuento de efectos
                    ref = ""
                    if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                        #Si el cliente tiene informada la cuenta de efectos descontados usamos esa.. si no usamos la del modo de pago
                        if line.partner_id.property_account_efectos_descontados:
                            cuenta_descuento_efectos = line.partner_id.property_account_efectos_descontados.id,

                        else:
                            cuenta_descuento_efectos = order.mode.cuenta_efectos_descontados.id,
                        partner_discount_line_id = self.pool.get('account.move.line').create(cr, uid, {
                            'name': line.move_line_id and line.move_line_id.name or '/',
                            'move_id': move_id,
                            'date': order.due_date,
                            'ref': order.reference,
                            'partner_id': line.partner_id and line.partner_id.id or False,
                            'account_id': cuenta_descuento_efectos[0],
                            'debit': ((amount > 0) and amount) or 0.0,
                            'credit': ((amount < 0) and -amount) or 0.0,
                            'journal_id': order.mode.journal.id,
                            'period_id': order.period_id.id,
                            'amount_currency': amount_currency,
                            'currency_id': move_currency_id,
                            'date_maturity': order.due_date,
                            'payment_order_check': True,
                            #'to_concile_account': cuenta_deuda_descuento_efectos,
                        }, context)



                    # Movimientos para devolución del dinero ongresado en el banco más gostos si hubiese

                    if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                        if (order.create_account_moves == 'descuento-efecto'):
                            cuenta_deuda_descuento_efectos = order.mode.cuenta_deuda_efectos_descontados.id
                        if (order.create_account_moves == 'factoring'):
                            cuenta_deuda_descuento_efectos = order.mode.cuenta_factoring.id

                        val_ef_descontados = {
                                   'name': line.move_line_id and line.move_line_id.name or '/',
                                   'move_id': move_id,
                                   'date': order.date_done,   ## a revisar TODO!!!!
                                   'ref': order.reference,
                                   'partner_id': line.partner_id and line.partner_id.id or False,
                                   'account_id': cuenta_deuda_descuento_efectos,
                                   'debit': ((amount<0) and -amount) or 0.0,
                                   'credit': ((amount>0) and amount) or 0.0,
                                   'journal_id': order.mode.journal.id,
                                   'period_id': order.period_id.id,
                                   'currency_id': currency_id,
                        }
                        partner_line_id_efectos_descontados = self.pool.get('account.move.line').create(cr, uid, val_ef_descontados, context, check=False)

                        if order.expense_moves:
                            self.pool.get('account.move.line').create(cr, uid, {
                                'name': line.move_line_id and line.move_line_id.name or '/',
                                'move_id': move_id,
                                'date': order.date_done,
                                'ref': order.reference,
                                'partner_id': line.partner_id and line.partner_id.id or False,
                                'account_id': order.mode.expense_account.id,
                                'debit': ((amount < 0) and -((amount*(order.mode.value_amount_unpaid/100)))) or 0.0,
                                'credit': ((amount > 0) and ((amount*(order.mode.value_amount_unpaid/100)))) or 0.0,
                                'journal_id': order.mode.journal.id,
                                'period_id': order.period_id.id,
                                'amount_currency': ((amount_currency*(order.mode.value_amount_unpaid/100))),
                                'currency_id': move_currency_id,
                            }, context)


                    if ((order.create_account_moves == 'factoring') or (order.create_account_moves == 'descuento-efecto')):
                        #Si el cliente tiene informada la cuenta de efectos descontados usamos esa.. si no usamos la del modo de pago

                        if order.create_account_moves == 'factoring':
                            name = unicode('Factoring /') + order.mode.journal.name
                        if order.create_account_moves == 'descuento-efecto':
                            name = unicode('Impago. de efectos /') + order.mode.journal.name

                        if line.type == 'payable':
                            line_amount = line.amount_currency or line.amount
                        else:
                            line_amount = -line.amount_currency or -line.amount

                        if line_amount >= 0:
                            account_id = order.mode.journal.default_credit_account_id.id
                        else:
                            account_id = order.mode.journal.default_debit_account_id.id
                            acc_cur = ((line_amount<=0) and order.mode.journal.default_debit_account_id) or line.account_id
                        if order.expense_moves:
                            amount = amount + (amount*(order.mode.value_amount_unpaid/100))

                        partner_bank_line_id = self.pool.get('account.move.line').create(cr, uid, {
                            'name': name,
                            'move_id': move_id,
                            'date': order.date_done,
                            'ref': order.reference,
                            'partner_id': line.partner_id and line.partner_id.id or False,
                            'account_id': account_id,
                            'debit': ((amount > 0) and amount) or 0.0,
                            'credit': ((amount < 0) and -amount) or 0.0,
                            'journal_id': order.mode.journal.id,
                            'period_id': order.period_id.id,
                            'amount_currency': amount_currency,
                            'currency_id': move_currency_id,
                            'date_maturity': order.due_date,
                            'payment_order_check': True,
                           # 'to_concile_account': cuenta_deuda_descuento_efectos,
                        }, context)

                    aml_ids = [x.id for x in self.pool.get('account.move').browse(cr, uid, move_id, context).line_id]
                    for x in self.pool.get('account.move.line').browse(cr, uid, aml_ids, context):
                        if x.state <> 'valid':
                            raise osv.except_osv(_('Error !'), _('Account move line "%s" is not valid') % x.name)
                        #self.pool.get('account.move.line').write(cr, uid, [x.id], {'ref':ref})

                if line.disccount_move_id and not line.disccount_move_id.reconcile_id:
                    ## If payment line of disccount has a related move line, we try to reconcile it with the move we just created.
                    lines_to_reconcile = [
                        partner_discount_line_id,
                    ]

                    ## Check if payment line move is already partially reconciled and use those moves in that case.
                    if line.disccount_move_id.reconcile_partial_id:
                        for rline in line.disccount_move_id.reconcile_partial_id.line_partial_ids:
                            lines_to_reconcile.append( rline.id )
                    else:
                        lines_to_reconcile.append( line.disccount_move_id.id )
                    amount = 0.0
                    for rline in self.pool.get('account.move.line').browse(cr, uid, lines_to_reconcile, context):
                        amount += rline.debit - rline.credit

                    currency = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id

                    if self.pool.get('res.currency').is_zero(cr, uid, currency, amount):
                        self.pool.get('account.move.line').reconcile(cr, uid, lines_to_reconcile, 'payment', context=context)
                    else:
                        self.pool.get('account.move.line').reconcile_partial(cr, uid, lines_to_reconcile, 'payment', context)

                if order.mode.journal.entry_posted:
                    self.pool.get('account.move').write(cr, uid, [move_id], {
                        'state':'posted',
                    }, context)

                    #self.pool.get('payment.line').write(cr, uid, [line.id], {
                        #'payment_move_id': move_id,
                    #}, context)
        return True
