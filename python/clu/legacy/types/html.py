"""
Generates HTML files via python declarations
"""

# Created 28-Jun-2008 by David Kirkby (dkirkby@uci.edu)

from getpass import getuser
from html import escape
from os.path import splitext
from socket import gethostname
from sys import argv
from time import ctime


class HTMLDocumentError(Exception):
    """
    Represents an error that occurs while declaring an HTML document.
    """
    pass


class Head:
    """
    Declares the head element of an HTML document.
    """
    iconTypes = {'.ico': 'image/vnd.microsoft.icon', '.gif': 'image/gif', '.png': 'image/png'}

    def __init__(self, title=None, base=None, icon=None, css=None, js=None, raw=None):
        self.type = type
        self.title = title
        self.base = base
        self.icon = icon
        self.css = []
        if css:
            self.css.append(css)
        self.js = []
        if js:
            self.js.append(js)
        self.raw = []
        if raw:
            self.raw.append(raw)

    def __str__(self):
        s = '<head>\n'
        s += '  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">\n'
        s += ('  <meta name="description" '
              'content="Document created automatically on %s by %s@%s using %s">\n' %
              (ctime(), getuser(), gethostname(), argv[0]))
        if self.title:
            s += '  <title>%s</title>\n' % self.title
        if self.base and ('href' in self.base or 'target' in self.base):
            s += '  <base'
            if 'href' in self.base:
                s += ' href="%s"' % self.base['href']
            else:
                s += ' href=""'
            # should check that target only uses [A-Za-z] or is one of the predefined
            # targets (http://htmlhelp.com/reference/html40/values.html#frametarget)
            if 'target' in self.base:
                s += ' target="%s"' % self.base['target']
            s += '>\n'
        if self.icon:
            iconExtension = splitext(self.icon)[1]
            if iconExtension not in Head.iconTypes:
                raise HTMLDocumentError('Unsupported icon extension: %s' % iconExtension)
            s += '  <link rel="icon" type="%s" href="%s" />\n' % (Head.iconTypes[iconExtension],
                                                                  self.icon)
        for style in self.css:
            # is this an external reference? look for a one-liner
            if style.count('\n') == 0:
                s += '  <link rel="stylesheet" type="text/css" href="%s">\n' % style
            else:
                s += '  <style type="text/css">\n%s</style>\n' % style
        for script in self.js:
            # is this an external reference? look for a one-liner
            if script.count('\n') == 0:
                s += '  <script type="text/javascript" src="%s"></script>\n' % script
            else:
                s += '  <script type="text/javascript">\n%s</script>\n' % script
        for raw in self.raw:
            s += '  %s\n' % raw
        s += '</head>\n'
        return s


class Text(str):
    """
    Declares a text node in an HTML document.
    """
    blockLevel = False

    def __new__(cls, obj, escapeMe=True):
        code = obj.encode('utf-8')
        if escapeMe:
            # HTML does not require escaping single quotes but we do this so that
            # the string representation of a document (or document fragment) can
            # be safely enclosed in single quotes.
            code = escape(code).replace("'", '&apos;')
        return str.__new__(cls, code)


class Entity(Text):
    """
    Declares text elements corresponding to the valid (X)HTML entities.
    """
    allowed = [  # http://en.wikipedia.org/wiki/List_of_XML_and_HTML_character_entity_references
        'quot', 'amp', 'apos', 'lt', 'gt', 'nbsp', 'iexcl', 'cent', 'pound', 'curren', 'yen',
        'brvbar', 'sect', 'uml', 'copy', 'ordf', 'laquo', 'not', 'shy', 'reg', 'macr', 'deg',
        'plusmn', 'sup2', 'sup3', 'acute', 'micro', 'para', 'middot', 'cedil', 'sup1', 'ordm',
        'raquo', 'frac14', 'frac12', 'frac34', 'iquest', 'Agrave', 'Aacute', 'Acirc', 'Atilde',
        'Auml', 'Aring', 'AElig', 'Ccedil', 'Egrave', 'Eacute', 'Ecirc', 'Euml', 'Igrave',
        'Iacute', 'Icirc', 'Iuml', 'ETH', 'Ntilde', 'Ograve', 'Oacute', 'Ocirc', 'Otilde', 'Ouml',
        'times', 'Oslash', 'Ugrave', 'Uacute', 'Ucirc', 'Uuml', 'Yacute', 'THORN', 'szlig',
        'agrave', 'aacute', 'acirc', 'atilde', 'auml', 'aring', 'aelig', 'ccedil', 'egrave',
        'eacute', 'ecirc', 'euml', 'igrave', 'iacute', 'icirc', 'iuml', 'eth', 'ntilde', 'ograve',
        'oacute', 'ocirc', 'otilde', 'ouml', 'divide', 'oslash', 'ugrave', 'uacute', 'ucirc',
        'uuml', 'yacute', 'thorn', 'yuml', 'OElig', 'oelig', 'Scaron', 'scaron', 'Yuml', 'fnof',
        'circ', 'tilde', 'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta', 'Theta',
        'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi', 'Omicron', 'Pi', 'Rho', 'Sigma', 'Tau',
        'Upsilon', 'Phi', 'Chi', 'Psi', 'Omega', 'alpha', 'beta', 'gamma', 'delta', 'epsilon',
        'zeta', 'eta', 'theta', 'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi', 'omicron', 'pi',
        'rho', 'sigmaf', 'sigma', 'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega', 'thetasym',
        'upsih', 'piv', 'ensp', 'emsp', 'thinsp', 'zwnj', 'zwj', 'lrm', 'rlm', 'ndash', 'mdash',
        'lsquo', 'rsquo', 'sbquo', 'ldquo', 'rdquo', 'bdquo', 'dagger', 'Dagger', 'bull', 'hellip',
        'permil', 'prime', 'Prime', 'lsaquo', 'rsaquo', 'oline', 'frasl', 'euro', 'image',
        'weierp', 'real', 'trade', 'alefsym', 'larr', 'uarr', 'rarr', 'darr', 'harr', 'crarr',
        'lArr', 'uArr', 'rArr', 'dArr', 'hArr', 'forall', 'part', 'exist', 'empty', 'nabla',
        'isin', 'notin', 'ni', 'prod', 'sum', 'minus', 'lowast', 'radic', 'prop', 'infin', 'ang',
        'and', 'or', 'cap', 'cup', 'int', 'there4', 'sim', 'cong', 'asymp', 'ne', 'equiv', 'le',
        'ge', 'sub', 'sup', 'nsub', 'sube', 'supe', 'oplus', 'otimes', 'perp', 'sdot', 'lceil',
        'rceil', 'lfloor', 'rfloor', 'lang', 'rang', 'loz', 'spades', 'clubs', 'hearts', 'diams'
    ]

    def __new__(cls, tag):
        if tag not in Entity.allowed:
            raise HTMLDocumentError('"%s" is not a recognized HTML entity' % tag)
        return Text.__new__(cls, '&' + tag + ';', escapeMe=False)


class Element(object):
    """
    Declares a generic (X)HTML document element.
    """
    indent = ''

    def __init__(self, *children, **attributes):
        self.tag = self.__class__.__name__.lower()
        if self.tag == 'element':
            raise HTMLDocumentError('"element" is a virtual base class for document elements')
        self.root = None
        self.children = []
        for child in children:
            self.append(child)
        self.attributes = {}
        for key in attributes:
            self.setAttribute(key, attributes[key])

    def setAttribute(self, key, value):
        if key == 'className':
            key = 'class'
        elif not key.islower():
            raise HTMLDocumentError('XHTML attributes must be lowercase: "%s"' % key)
        if key in self.attributes:
            raise HTMLDocumentError(
                'attribute has already been set: %s = %s' % (key, self.attributes[key]))
        # We always output attribute values in double quotes so the [&,<,"] characters
        # must be escaped according to http://www.w3.org/TR/REC-xml/#NT-AttValue.
        # We additionally escape single quotes ['] so that an HTML document or
        # fragment can be safely single quoted (but not double quoted).
        safe_value = (value.replace('"', '&quot;').replace("'",
                                                           '&apos;').replace('<', '&gt').replace(
                                                               '&', '&amp;'))
        self.attributes[key] = safe_value
        if key == 'id' and self.root is not None:
            self.root.registerID(value, self)

    def __getitem__(self, key):
        try:
            return self.attributes[key]
        except KeyError:
            raise HTMLDocumentError('"%s" element has no attribute "%s"' % (self.tag, key))

    def __setitem__(self, key, value):
        self.setAttribute(key, value)

    def setRoot(self, root):
        """
        Assigns or reassigns this element to a document root.

        An element can be added to multiple documents or multiple times to the
        same document (unless it has an 'id' attribute).
        """
        self.root = root
        if 'id' in self.attributes and root is not None:
            self.root.registerID(self.attributes['id'], self)
        for child in self.children:
            if isinstance(child, Element):
                child.setRoot(root)

    def append(self, child):
        if not isinstance(child, Element) and not isinstance(child, Text):
            child = Text(child)
        self.children.append(child)
        if isinstance(child, Element) and self.root is not None:
            child.setRoot(self.root)

    def extend(self, children):
        for child in children:
            self.append(child)

    def __str__(self):
        """
        Return a string representation of this element.

        Note that the returned string will contain double quotes around all attribute
        values but will not contain any single quotes (except possibly via an
        un-escaped text node), so can be safely enclosed in single quotes.
        """
        s = ''
        if self.blockLevel:
            s += Element.indent
        s += '<%s' % self.tag
        for attrib in self.attributes:
            s += ' %s="%s"' % (attrib, self.attributes[attrib])
        if len(self.children) == 0:
            s += ' />'
        else:
            s += '>'
            blocked = True in [child.blockLevel for child in self.children]
            if self.blockLevel and blocked:
                s += '\n'
                Element.indent += '  '
            for child in self.children:
                s += child.__str__()
            if self.blockLevel and blocked:
                Element.indent = Element.indent[:-2]
                s += Element.indent
            s += '</%s>' % self.tag
        if self.blockLevel:
            s += '\n'
        return s


# Define the allowed HTML4 block-level elements according to
# http://htmlhelp.com/reference/html40/block.html
# Python symbols are capitalized to avoid conflicts with builtin names (like 'object')
for tag in [
        # defined as block level in HTML4
        'address',
        'blockquote',
        'div',
        'dl',
        'fieldset',
        'form',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'hr',
        'noscript',
        'ol',
        'p',
        'pre',
        'table',
        'ul',
        # are considered block level since they can contain block-level children
        'dd',
        'dt',
        'li',
        'tbody',
        'td',
        'tfoot',
        'th',
        'thead',
        'tr',
        # are block level when they contain block-level children
        'button',
        'del',
        'ins',
        'map',
        'object',
        'script',
        # not listed as either block-level or inline at htmlhelp.com
        'body',
        # not HTML4 standard
        'embed'
]:
    globals()[tag.capitalize()] = type(tag.capitalize(), (Element, ), {'blockLevel': True})

# Define the allowed HTML4 inline elements according to
# http://htmlhelp.com/reference/html40/inline.html
# Python symbols are capitalized to avoid conflicts with builtin names (like 'object')
for tag in [
        # defined as inline in HTML4
        'a',
        'abbr',
        'acronym',
        'b',
        'bdo',
        'big',
        'br',
        'cite',
        'code',
        'dfn',
        'em',
        'i',
        'img',
        'input',
        'kbd',
        'label',
        'q',
        'samp',
        'select',
        'small',
        'span',
        'strong',
        'sub',
        'sup',
        'textarea',
        'tt',
        'var',
        # not listed as either block-level or inline at htmlhelp.com
        'option',
        'optgroup'
]:
    globals()[tag.capitalize()] = type(tag.capitalize(), (Element, ), {'blockLevel': False})


class HTMLDocument:
    """
    Declares an (X)HTML document.
    """

    def __init__(self, head, body):
        self.head = head
        self.body = body
        self.registry = {}
        self.body.setRoot(self)

    def registerID(self, id, element):
        if id in self.registry:
            raise HTMLDocumentError('id already registered for this document: "%s"' % id)
        self.registry[id] = element

    def __getitem__(self, key):
        try:
            return self.registry[key]
        except KeyError:
            raise HTMLDocumentError('Document has no element registered with id "%s"' % key)

    def __str__(self):
        return ('''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">\n''' + self.head.__str__() +
                self.body.__str__() + '\n</html>')
