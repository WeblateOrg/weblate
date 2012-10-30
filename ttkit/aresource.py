#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2012 Michal Čihař
#
# This file is part of the Translate Toolkit.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.

"""module for handling Android resource files"""

from lxml import etree

from StringIO import StringIO

import re
import pdb

from translate.storage import lisa
from translate.storage import base
from translate.lang import data

EOF = None
WHITESPACE = ' \n\t' # Whitespace that we collapse
MULTIWHITESPACE = re.compile('[ \n\t]{2}')
OPEN_TAG_TO_ESCAPE = re.compile('<(?!/?\S*>)')

class AndroidResourceUnit(base.TranslationUnit):
    """A single term in the Android resource file."""
    rootNode = "string"
    languageNode = "string"

    def __init__(self, source, empty=False, xmlelement = None, **kwargs):
        if xmlelement is not None:
            self.xmlelement = xmlelement
        else:
            self.xmlelement = etree.Element(self.rootNode)
            self.xmlelement.tail = '\n'
        if source is not None:
            self.setid(source)
        super(AndroidResourceUnit, self).__init__(source)

    def getid(self):
        return self.xmlelement.get("name")

    def getcontext(self):
        return self.xmlelement.get("name")

    def setid(self, newid):
        return self.xmlelement.set("name", newid)

    def unescape(self, text):
        '''
        Remove escaping from Android resource.

        Code stolen from android2po
        <https://github.com/miracle2k/android2po>
        '''
        # Return text for empty elements
        if text is None:
            return ''

        # We need to collapse multiple whitespace while paying
        # attention to Android's quoting and escaping.
        space_count = 0
        active_quote = False
        active_percent = False
        active_escape = False
        formatted = False
        i = 0
        text = list(text) + [EOF]
        while i < len(text):
            c = text[i]

            # Handle whitespace collapsing
            if c is not EOF and c in WHITESPACE:
                space_count += 1
            elif space_count > 1:
                # Remove duplicate whitespace; Pay attention: We
                # don't do this if we are currently inside a quote,
                # except for one special case: If we have unbalanced
                # quotes, e.g. we reach eof while a quote is still
                # open, we *do* collapse that trailing part; this is
                # how Android does it, for some reason.
                if not active_quote or c is EOF:
                    # Replace by a single space, will get rid of
                    # non-significant newlines/tabs etc.
                    text[i-space_count : i] = ' '
                    i -= space_count - 1
                space_count = 0
            elif space_count == 1:
                # At this point we have a single whitespace character,
                # but it might be a newline or tab. If we write this
                # kind of insignificant whitespace into the .po file,
                # it will be considered significant on import. So,
                # make sure that this kind of whitespace is always a
                # standard space.
                text[i-1] = ' '
                space_count = 0
            else:
                space_count = 0

            # Handle quotes
            if c == '"' and not active_escape:
                active_quote = not active_quote
                del text[i]
                i -= 1

            # If the string is run through a formatter, it will have
            # percentage signs for String.format
            if c == '%' and not active_escape:
                active_percent = not active_percent
            elif not active_escape and active_percent:
                formatted = True
                active_percent = False

            # Handle escapes
            if c == '\\':
                if not active_escape:
                    active_escape = True
                else:
                    # A double-backslash represents a single;
                    # simply deleting the current char will do.
                    del text[i]
                    i -= 1
                    active_escape = False
            else:
                if active_escape:
                    # Handle the limited amount of escape codes
                    # that we support.
                    # TODO: What about \r, or \r\n?
                    if c is EOF:
                        # Basically like any other char, but put
                        # this first so we can use the ``in`` operator
                        # in the clauses below without issue.
                        pass
                    elif c == 'n' or c == 'N':
                        text[i-1 : i+1] = '\n' # an actual newline
                        i -= 1
                    elif c == 't' or c == 'T':
                        text[i-1 : i+1] = '\t' # an actual tab
                        i -= 1
                    elif c == ' ':
                        text[i-1 : i+1] = ' ' # an actual space
                        i -= 1
                    elif c in '"\'@':
                        text[i-1 : i] = '' # remove the backslash
                        i -= 1
                    elif c == 'u':
                        # Unicode sequence. Android is nice enough to deal
                        # with those in a way which let's us just capture
                        # the next 4 characters and raise an error if they
                        # are not valid (rather than having to use a new
                        # state to parse the unicode sequence).
                        # Exception: In case we are at the end of the
                        # string, we support incomplete sequences by
                        # prefixing the missing digits with zeros.
                        # Note: max(len()) is needed in the slice due to
                        # trailing ``None`` element.
                        max_slice = min(i+5, len(text)-1)
                        codepoint_str = "".join(text[i+1 : max_slice])
                        if len(codepoint_str) < 4:
                            codepoint_str = u"0" * (4-len(codepoint_str)) + codepoint_str
                        try:
                            # We can't trust int() to raise a ValueError,
                            # it will ignore leading/trailing whitespace.
                            if not codepoint_str.isalnum():
                                raise ValueError(codepoint_str)
                            codepoint = unichr(int(codepoint_str, 16))
                        except ValueError:
                            raise ValueError('bad unicode escape sequence')

                        text[i-1 : max_slice] = codepoint
                        i -= 1
                    else:
                        # All others, remove, like Android does as well.
                        text[i-1 : i+1] = ''
                        i -= 1
                    active_escape = False

            i += 1

        # Join the string together again, but w/o EOF marker
        return "".join(text[:-1])

    def escape(self, text):
        '''
        Escape all the characters which need to be escaped in an Android XML file.
        '''
        if text is None:
            return
        if len(text) == 0:
            return ''
        text = text.replace('\\', '\\\\')
        text = text.replace('\n', '\\n')
        # This will add non intrusive real newlines to
        # ones in translation improving readability of result
        text = text.replace(' \\n', '\n\\n')
        text = text.replace('\t', '\\t')
        text = text.replace('\'', '\\\'')
        text = text.replace('"', '\\"')

        # @ needs to be escaped at start
        if text.startswith('@'):
            text = '\\@' + text[1:]
        # Quote strings with more whitespace
        if text[0] in WHITESPACE or text[-1] in WHITESPACE or len(MULTIWHITESPACE.findall(text)) > 0:
            return '"%s"' % text
        return text

    def setsource(self, source):
        super(AndroidResourceUnit, self).setsource(source)

    def getsource(self, lang=None):
        if (super(AndroidResourceUnit, self).source is None):
            return self.target
        else:
            return super(AndroidResourceUnit, self).source

    source = property(getsource, setsource)

    def settarget(self, target):
        if '<' in target:
            # Handle text with markup
            target = self.escape(target).replace('&', '&amp;')
            target = OPEN_TAG_TO_ESCAPE.sub('&lt;', target)
            # Parse new XML
            newstring = etree.parse(StringIO('<string>' + target + '</string>')).getroot()
            # Update text
            self.xmlelement.text = newstring.text
            # Remove old elements
            for x in self.xmlelement.iterchildren():
                self.xmlelement.remove(x)
            # Add new elements
            for x in newstring.iterchildren():
                self.xmlelement.append(x)
        else:
            # Handle text only
            self.xmlelement.text = self.escape(target)
        super(AndroidResourceUnit, self).settarget(target)

    def gettarget(self, lang=None):
        # Grab inner text
        target = (self.xmlelement.text or u'')
        # Include markup as well
        target += u''.join([data.forceunicode(etree.tostring(child, encoding = 'utf-8')) for child in self.xmlelement.iterchildren()])
        return self.unescape(data.forceunicode(target))

    target = property(gettarget, settarget)


    def getlanguageNode(self, lang=None, index=None):
        return self.xmlelement

    def createfromxmlElement(cls, element):
        term = cls(None, xmlelement = element)
        return term
    createfromxmlElement = classmethod(createfromxmlElement)

    # Notes are handled as previous sibling comments.
    def addnote(self, text, origin=None, position="append"):
        if origin in ['programmer', 'developer', 'source code', None]:
            self.xmlelement.addprevious(etree.Comment(text))
        else:
            return super(AndroidResourceUnit, self).addnote(text, origin=origin,
                                                 position=position)

    def getnotes(self, origin=None):
        if origin in ['programmer', 'developer', 'source code', None]:
            comments = []
            if (self.xmlelement is not None):
                prevSibling = self.xmlelement.getprevious()
                while ((prevSibling is not None) and (prevSibling.tag is etree.Comment)):
                    comments.insert(0, prevSibling.text)
                    prevSibling = prevSibling.getprevious()

            return u'\n'.join(comments)
        else:
            return super(AndroidResourceUnit, self).getnotes(origin)

    def removenotes(self):
        if ((self.xmlelement is not None) and (self.xmlelement.getparent is not None)):
            prevSibling = self.xmlelement.getprevious()
            while ((prevSibling is not None) and (prevSibling.tag is etree.Comment)):
                prevSibling.getparent().remove(prevSibling)
                prevSibling = self.xmlelement.getprevious()

        super(AndroidResourceUnit, self).removenotes()

    def __str__(self):
        return etree.tostring(self.xmlelement, pretty_print=True,
                              encoding='utf-8')

    def __eq__(self, other):
        return (str(self) == str(other))

class AndroidResourceFile(lisa.LISAfile):
    """Class representing a Android resource file store."""
    UnitClass = AndroidResourceUnit
    Name = _("Android Resource")
    Mimetypes = ["application/xml"]
    Extensions = ["xml"]
    rootNode = "resources"
    bodyNode = "resources"
    XMLskeleton = '''<?xml version="1.0" encoding="utf-8"?>
<resources></resources>'''

    def initbody(self):
        """Initialises self.body so it never needs to be retrieved from the
        XML again."""
        self.namespace = self.document.getroot().nsmap.get(None, None)
        self.body = self.document.getroot()
