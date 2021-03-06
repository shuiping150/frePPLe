# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 by Johan De Taeye, frePPLe bvba
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import openerp
import logging
from datetime import datetime, timedelta
from xml.etree.cElementTree import iterparse

logger = logging.getLogger(__name__)


class importer(object):

  def __init__(self, req, **kwargs):
    self.req = req
    self.database = kwargs.get('database', None)
    authmeth, auth = req.httprequest.headers['authorization'].split(' ', 1)
    if authmeth.lower() != 'basic':
      raise Exception("No authentication header")
    auth = auth.strip().decode('base64')
    user, password = auth.split(':', 1)
    if not self.database or not user or not password:
      raise Exception("Authentication error")
    if not self.req.session.authenticate(self.database, user, password):
      raise Exception("Odoo authentication failed")
    if 'language' in kwargs:
      # If not set we use the default language of the user
      self.req.session.context['lang'] = kwargs['language']
    self.company = kwargs.get('company', None)
    self.datafile = kwargs.get('frePPLe plan')


  def run(self):
    msg = []

    # Look up the company id
    company_id = None
    m = self.req.session.model('res.company')
    for i in m.search([('name', '=', self.company)], context=self.req.session.context):
      company_id = i
    if not company_id:
      raise Exception("Invalid company name argument")

    # Cancel previous draft purchase quotations
    m = self.req.session.model('purchase.order')
    ids = m.search(
      [('state', '=', 'draft'), ('origin', '=', 'frePPLe')],
      context=self.req.session.context
      )
    m.unlink(ids, self.req.session.context)
    msg.append("Removed %s old draft purchase quotations" % len(ids))

    # Cancel previous draft procurement orders
    proc_order = self.req.session.model('procurement.order')
    ids = proc_order.search(
      ['|', ('state', '=', 'draft'), ('state', '=', 'cancel'), ('origin', '=', 'frePPLe')],
      context=self.req.session.context
      )
    proc_order.unlink(ids, self.req.session.context)
    msg.append("Removed %s old draft procurement orders" % len(ids))

    # Cancel previous draft manufacturing orders
    mfg_order = self.req.session.model('mrp.production')
    ids = mfg_order.search(
      ['|', ('state', '=', 'draft'), ('state', '=', 'cancel'), ('origin', '=', 'frePPLe')],
      context=self.req.session.context
      )
    mfg_order.unlink(ids, self.req.session.context)
    msg.append("Removed %s old draft manufacturing orders" % len(ids))

    # Parsing the XML data file
    countproc = 0
    countmfg = 0
    for event, elem in iterparse(self.datafile, events=('start', 'end')):
      if event == 'end' and elem.tag == 'operationplan':
        uom_id, item_id = elem.get('item').split(',')
        n = elem.get('operation')
        try:
          if n.startswith('Purchase'):
            # Create purchase quotation
            x = proc_order.create({
              'name': n,
              'product_qty': elem.get("quantity"),
              'date_planned': elem.get("end"),
              'product_id': int(item_id),
              'company_id': company_id,
              'product_uom': int(uom_id),
              'location_id': int(elem.get('location')),
              'procure_method': 'make_to_order',
              # : elem.get('criticality'),
              'origin': 'frePPLe'
              })
            proc_order.action_confirm([x], context=self.req.session.context)
            proc_order.action_po_assign([x], context=self.req.session.context)
            countproc += 1
          else:
            # Create manufacturing order
            x = mfg_order.create({
              'product_qty': elem.get("quantity"),
              'date_planned': elem.get("end"),
              'product_id': int(item_id),
              'company_id': company_id,
              'product_uom': int(uom_id),
              'location_src_id': int(elem.get('location')),
              'product_uos_qty': False,
              'product_uos': False,
              'bom_id': False,
              # : elem.get('criticality'),
              'origin': 'frePPLe'
              })
            mfg_order.action_compute([x], context=self.req.session.context)
            countmfg += 1
        except Exception as e:
          msg.append(str(e))
        # Remove the element now to keep the DOM tree small
        root.clear()
      elif event == 'start' and elem.tag == 'operationplans':
        # Remember the root element
        root = elem

    # Be polite, and reply to the post
    msg.append("Processed %s uploaded procurement orders" % countproc)
    msg.append("Processed %s uploaded manufacturing orders" % countmfg)
    return '\n'.join(msg)
