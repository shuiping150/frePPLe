#
# Copyright (C) 2007 by Johan De Taeye
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser
# General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#

# file : $URL$
# revision : $LastChangedRevision$  $LastChangedBy$
# date : $LastChangedDate$

from decimal import Decimal

from django.template import Library, Node, NodeList, Variable, resolve_variable
from django.template import VariableDoesNotExist, TemplateSyntaxError
from django.template.defaultfilters import stringfilter
from django.conf import settings
from django.contrib.admin.views.main import quote
from django.utils.translation import ugettext as _
from django.utils.http import urlquote
from django.utils.encoding import iri_to_uri, force_unicode
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.contrib.admin import sites

HOMECRUMB = '<a href="/admin/">%s</a>'

register = Library()
variable_title = Variable("title")
variable_request = Variable("request")
variable_popup = Variable("is_popup")

#
# A tag to find all models a user is allowed to see
#

class ModelsNode(Node):
    def __init__(self, appname, adminsite, varname):
        self.varname = varname
        self.appname = appname
        try:
          dot = adminsite.rindex('.')
          self.adminsite = getattr(__import__(adminsite[:dot], {}, {}, ['']), adminsite[dot+1:])
        except:
          self.adminsite = sites.site

    def render(self, context):
        from django.db import models
        from django.utils.text import capfirst
        user = context['user']
        model_list = []
        if user.has_module_perms(self.appname):
          for m in models.get_models(models.get_app(self.appname)):
             # Verify if the model is allowed to be displayed in the admin ui and
             # check the user has appropriate permissions to access it
             if m in self.adminsite._registry and user.has_perm("%s.%s" % (self.appname, m._meta.get_change_permission())):
                 model_list.append({
                   'name': capfirst(m._meta.verbose_name_plural),
                   'admin_url': '/admin/%s/%s/' % (self.appname, m.__name__.lower()),
                   })
          model_list.sort()
        context[self.varname] = model_list
        return ''


def get_models(parser, token):
    """
    Returns a list of output models to which the user has permissions.

    Syntax::

        {% get_models from [application_name] [admin_site] as [context_var_containing_app_list] %}
        {% get_models from [application_name] default as [context_var_containing_app_list] %}

    Example usage::

        {% get_models from output output.admin.site as modelsOut %}
        {% get_models from output default as modelsOut %}
    """
    tokens = token.contents.split()
    if len(tokens) < 6:
        raise TemplateSyntaxError, "'%s' tag requires 6 arguments" % tokens[0]
    if tokens[1] != 'from':
        raise TemplateSyntaxError, "First argument to '%s' tag must be 'from'" % tokens[0]
    if tokens[4] != 'as':
        raise TemplateSyntaxError, "Third argument to '%s' tag must be 'as'" % tokens[0]
    return ModelsNode(tokens[2],tokens[3],tokens[5])

register.tag('get_models', get_models)


#
# A tag to create breadcrumbs on your site
#

class CrumbsNode(Node):
    r'''
    A generic breadcrumbs framework.

    Usage in your templates:
    {% crumbs %}

    The admin app already defines a block for crumbs, so the typical usage of the
    crumbs tag is as follows:
    {%block breadcrumbs%}<div class="breadcrumbs">{%crumbs%}</div>{%endblock%}

    When the context variable 'reset_crumbs' is defined and set to True, the trail of
    breadcrumbs is truncated and restarted.
    The variable can be set either as an extra context variable in the view
    code, or with the 'set' template tag in the template:
    {% set reset_crumbs "True" %}
    '''
    def render(self, context):
        global HOMECRUMB
        global variable_title
        try: req = context['request']
        except: return ''  # No request found in the context: no crumbs...
        # Pick up the current crumbs from the session cookie
        try: cur = req.session['crumbs']
        except: cur = [(_('Home'),HOMECRUMB % _('Home'))]

        # Check if we need to reset the crumbs
        try:
          if context['reset_crumbs']: cur = [(_('Home'),HOMECRUMB % _('Home'))]
        except: pass

        # Pop from the stack if the same url is already in the crumbs
        try: title = variable_title.resolve(context)
        except: title = req.get_full_path()
        # A special case to work around the hardcoded title of the main admin page
        if title == _('Site administration'): title = _('Home')
        cnt = 0
        for i in cur:
           if i[0] == title:
             cur = cur[0:cnt]   # Pop all remaining elements from the stack
             break
           cnt += 1

        # Push current url on the stack
        cur.append( (unicode(title),'<a href="%s%s">%s</a>' % (
          urlquote(req.path),
          req.GET and ('?' + iri_to_uri(req.GET.urlencode())) or '',
          unicode(escape(title))
          )))

        # Update the current session
        req.session['crumbs'] = cur

        # Now create HTML code to return
        return '  >  '.join([i[1] for i in cur])

def do_crumbs(parser, token):
    return CrumbsNode()

register.tag('crumbs', do_crumbs)


#
# A tag to create a superlink, which is a hyperlink with a context menu
#

class SuperLink(Node):
  def __init__(self, varname, type, key):
    self.var = Variable(varname)
    self.type = type
    self.key = key

  def render(self, context):
    value = self.var.resolve(context)
    if value == '' or value == None:
      return mark_safe('')
    else:
      try: popup = variable_popup.resolve(context)
      except: popup = False
      if popup:
        if self.key:
          # Key field in a popup window: the link won't display a context menu.
          # It will close the popup window instead.
          return mark_safe('<a href="" onclick="opener.dismissRelatedLookupPopup(window, %s); return false;">%s</a>' % (repr(force_unicode(value))[1:], escape(value)))
        else:
          # Non-key field in a popup window
          return mark_safe(escape(value))
      else:
        # Not a popup window
        return mark_safe('<a href="#" class="%s">%s</a>' % (self.type, escape(value)))

def superlinknode(parser, token):
  from re import split
  bits = split(r'\s+', token.contents, 3)
  argumentcount = len(bits)
  if argumentcount == 3:
    return SuperLink(bits[1],bits[2],False)
  elif argumentcount == 4:
    if bits[3] == 'key':
      return SuperLink(bits[1],bits[2],True)
    else:
      TemplateSyntaxError, "'%s' only accepts 'key' as third optional argument" % bits[0]
  else:
    raise TemplateSyntaxError, "'%s' tag requires 2 or 3 arguments" % bits[0]

register.tag('superlink',superlinknode)


#
# A tag to update a context variable
#

class SetVariable(Node):
  def __init__(self, varname, value):
    self.varname = varname
    self.value = value

  def render(self, context):
    var = Variable(self.value).resolve(context)
    if var:
      context[self.varname] = var
    else:
      context[self.varname] = context[self.value]
    return ''


def set_var(parser, token):
  r'''
  Example:
  {% set category_list category.categories.all %}
  {% set dir_url "../" %}
  {% set type_list "table" %}
  '''
  from re import split
  bits = split(r'\s+', token.contents, 2)
  if len(bits) < 2:
      raise TemplateSyntaxError, "'%s' tag requires two arguments" % bits[0]
  return SetVariable(bits[1],bits[2])

register.tag('set', set_var)


#
# A simple tag returning the frePPLe version
#

@register.simple_tag
def version():
  '''
  A simple tag returning the version of the frepple application.
  '''
  return settings.FREPPLE_VERSION

version.is_safe = True


#
# A filter to format a duration 
#

def duration(value): 
  try:
    if value == None: return ''
    value = Decimal(force_unicode(value))  
    if value == 0: return '0 s'
    if value % 604800 == 0: return '%.2f w' % (value/Decimal('604800.0'))
    if value % 3600 != 0 and value < 86400: return '%.2f s' % value
    if value % 86400 != 0 and value < 604800: return '%.2f h' % (value/Decimal('3600'))
    return '%.2f d' % (value/Decimal('86400'))
  except Exception, e:
    print e
    return ''
    
duration.is_safe = True
register.filter('duration', duration)


#
# Output the contents of the block if depending on how two objects compare 
# to each other.
# Examples::
#
#   {% iflessthan alpha bravo %}
#       ...
#   {% endiflessthan %}
#
#   {% ifgreaterthan alpha bravo %}
#       ...
#   {% else %}
#       ...
#   {% endifnotequal %}
#   
#   {% iflessthanorequal alpha bravo %}
#       ...
#   {% endiflessthanorequal %}
#   
#   {% ifgreaterthanorequal alpha bravo %}
#       ...
#   {% endifgreaterthanorequal %}
#
# The code is copied from the following site - where it is licensed under BSD
#  http://nrcfosshelpline.in/code/browser/trunk/web/templatetags/base_utils.py
#

class CompareNode(Node):
    def __init__(self, var1, var2, nodelist_true, nodelist_false, lessthan, orequal):
        self.var1, self.var2 = var1, var2
        self.nodelist_true, self.nodelist_false = nodelist_true, nodelist_false
        self.lessthan = lessthan
        self.orequal = orequal

    def render(self, context):
        try:
            val1 = resolve_variable(self.var1, context)
        except VariableDoesNotExist:
            val1 = None
        try:
            val2 = resolve_variable(self.var2, context)
        except VariableDoesNotExist:
            val2 = None
        try:
            if self.lessthan:
                if self.orequal:
                    if val1 <= val2:
                        return self.nodelist_true.render(context)
                else:
                    if val1 < val2:
                        return self.nodelist_true.render(context)
            else:
                if self.orequal:
                    if val1 >= val2:
                        return self.nodelist_true.render(context)
                else:
                    if val1 > val2:
                        return self.nodelist_true.render(context)
        except:
            pass
        return self.nodelist_false.render(context)

def do_compare(parser, token, lessthan, orequal):
    bits = list(token.split_contents())
    if len(bits) != 3:
        raise TemplateSyntaxError, "%r takes two arguments" % bits[0]
    end_tag = 'end' + bits[0]
    nodelist_true = parser.parse(('else', end_tag))
    token = parser.next_token()
    if token.contents == 'else':
        nodelist_false = parser.parse((end_tag,))
        parser.delete_first_token()
    else:
        nodelist_false = NodeList()
    return CompareNode(bits[1], bits[2], nodelist_true, nodelist_false, lessthan, orequal)

def iflessthan(parser, token):
    return do_compare(parser, token, True, False)
register.tag('iflessthan', iflessthan)

def ifgreaterthan(parser, token):
    return do_compare(parser, token, False, False)
register.tag('ifgreaterthan', ifgreaterthan)

def iflessthanorequal(parser, token):
    return do_compare(parser, token, True, True)
register.tag('iflessthanorequal', iflessthanorequal)

def ifgreaterthanorequal(parser, token):
    return do_compare(parser, token, False, True)
register.tag('ifgreaterthanorequal', ifgreaterthanorequal)
