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

from osv import osv, fields

class check_paid_wizard(osv.osv_memory):
    _name = 'check.paid.wizard'
    _description = 'Check payments in orders'   


    def _check_paid(self, cr, uid, ids, context=None):
        """
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        """
        line_obj = self.pool.get('payment.line')
        #As this function is in a new thread, i need to open a new cursor, because the old one may be closed
        new_cr = pooler.get_db(cr.dbname).cursor()
        for line in self.browse(new_cr, uid, ids, context=context):
            line_obj.check_paid(new_cr, uid, automatic=False, use_new_cursor=new_cr.dbname,\
                    context=context)
        #close the new cursor
        new_cr.close()
        return {}

    def check_paid(self, cr, uid, ids, context=None):
        """
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        """
        threaded_calculation = threading.Thread(target=self._check_paid, args=(cr, uid, ids, context))
        threaded_calculation.start()
        return {'type': 'ir.actions.act_window_close'}

check_paid_wizard()

