"""Specific file formats for XWiki"""

import re
from copy import deepcopy
from xml.etree import ElementTree
from xml.sax.saxutils import escape, unescape
from django.utils.functional import cached_property
from translate.storage.properties import xwikifile
from translate.misc import quote
from weblate.formats.ttkit import PropertiesFormat, PropertiesUnit

XML_HEADER = """<?xml version="1.1" encoding="UTF-8"?>

<!--
 * See the NOTICE file distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as
 * published by the Free Software Foundation; either version 2.1 of
 * the License, or (at your option) any later version.
 *
 * This software is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this software; if not, write to the Free
 * Software Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
 * 02110-1301 USA, or see the FSF site: http://www.fsf.org.
-->

"""


class XWikiUnit(PropertiesUnit):
    """
        Inspired from PropertiesUnit, allow to override the methods to use the right
        XWikiDialect methods for decoding properties.
    """

    @cached_property
    def source(self):
        # Need to decode property encoded string
        return quote.xwiki_properties_decode(super().source)

    @cached_property
    def target(self):
        """Return target string from a Translate Toolkit unit."""
        if self.unit is None:
            return ""
        # Need to decode property encoded string
        # This is basically stolen from
        # translate.storage.properties.propunit.gettarget
        # which for some reason does not return translation
        value = quote.xwiki_properties_decode(self.unit.value)
        value = re.sub("\\\\ ", " ", value)
        return value


class XWikiPropertiesFormat(PropertiesFormat):
    """
    Represents an XWiki Java Properties translation file.
    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiJavaProperties
    """

    unit_class = XWikiUnit
    name = 'XWiki Java Properties'
    format_id = 'xwiki-java-properties'
    loader = xwikifile
    language_format = 'java'

    def save_content(self, handle):
        current_units = self.all_units
        self.store.units = []
        # Ensure that not translated units are saved too as missing properties.
        for unit in current_units:
            if unit.unit is None:
                if not unit.has_content():
                    unit.unit = unit.mainunit
                else:
                    missingunit, added = self.find_unit(unit.context, unit.source)
                    unit.unit = missingunit.unit
                    unit.unit.missing = True
            self.add_unit(unit.unit)

        self.store.serialize(handle)


class XWikiPageProperties(xwikifile):
    Name = "XWiki Page Properties"
    Extensions = ['xml']

    def __init__(self, *args, **kwargs):
        kwargs['personality'] = "java-utf8"
        kwargs['encoding'] = "utf-8"
        super(XWikiPageProperties, self).__init__(*args, **kwargs)
        self.root = None

    def parse(self, propsrc):
        if propsrc != b"\n":
            self.root = ElementTree.XML(propsrc)
            content = ""\
                .join(self.root.find("content").itertext())
            content = unescape(content).encode(self.encoding)
            super(XWikiPageProperties, self).parse(content)

    def set_xwiki_xml_attributes(self, newroot):
        for e in newroot.findall("object"):
            newroot.remove(e)
        for e in newroot.findall("attachment"):
            newroot.remove(e)
        newroot.find("translation").text = "1"
        newroot.find("language").text = self.gettargetlanguage()

    def write_xwiki_xml(self, newroot, out):
        xml_content = ElementTree.tostring(newroot,
                                           encoding=self.encoding,
                                           method="xml")
        out.write(XML_HEADER.encode(self.encoding))
        out.write(xml_content)

    def serialize(self, out):
        newroot = deepcopy(self.root)
        newroot.find("content").text = escape(
            "".join(unit.getoutput() for unit in self.units))
        self.set_xwiki_xml_attributes(newroot)
        self.write_xwiki_xml(newroot, out)


class XWikiPagePropertiesFormat(XWikiPropertiesFormat):
    """
    Represents an XWiki Page Properties translation file.
    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiPageProperties
    """

    name = 'XWiki Page Properties'
    format_id = 'xwiki-page-properties'
    loader = XWikiPageProperties
    language_format = 'java'

    @classmethod
    def fixup(cls, store):
        """Force encoding to UTF-8 since we inherit from XWikiProperties which force
        for ISO-8859-1.
        """
        store.encoding = 'utf-8'

    def save_content(self, handle):
        if self.store.root is None:
            self.store.root = self.template_store.store.root
        super(XWikiPagePropertiesFormat, self).save_content(handle)


class XWikiFullPage(XWikiPageProperties):
    Name = "XWiki Full Page"

    def parse(self, propsrc):
        if propsrc != b"\n":
            self.root = ElementTree.XML(propsrc)
            content = ""\
                .join(self.root.find("content").itertext())\
                .replace("\n", "\\n")
            title = ""\
                .join(self.root.find("title").itertext())
            forparsing = "title={}\ncontent={}"\
                .format(unescape(title), unescape(content))\
                .encode(self.encoding)
            super(XWikiPageProperties, self).parse(forparsing)

    def serialize(self, out):
        unit_title = self.findid("title")
        unit_content = self.findid("content")

        newroot = deepcopy(self.root)
        newroot.find("title").text = unit_title.target
        newroot.find("content").text = unit_content.target.replace("\\n", "\n")
        self.set_xwiki_xml_attributes(newroot)
        self.write_xwiki_xml(newroot, out)


class XWikiFullPageFormat(XWikiPagePropertiesFormat):
    """
    Represents an XWiki Full Page translation file.
    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiFullContentTranslation
    """

    name = 'XWiki Full Page'
    format_id = 'xwiki-fullpage'
    loader = XWikiFullPage
    language_format = 'java'
