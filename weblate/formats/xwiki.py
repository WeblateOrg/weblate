"""Specific file formats for XWiki"""

import re

from django.utils.functional import cached_property
from translate.misc import quote
from weblate.formats.ttkit import PropertiesFormat, PropertiesUnit


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
    loader = ("properties", "xwikifile")
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


class XWikiPagePropertiesFormat(XWikiPropertiesFormat):
    """
    Represents an XWiki Page Properties translation file.
    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiPageProperties
    """

    name = 'XWiki Page Properties'
    format_id = 'xwiki-page-properties'
    loader = ("properties", "XWikiPageProperties")
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


class XWikiFullPageFormat(XWikiPagePropertiesFormat):
    """
    Represents an XWiki Full Page translation file.
    This format specification is detailed in
    https://dev.xwiki.org/xwiki/bin/view/Community/XWiki%20Translations%20Formats/#HXWikiFullContentTranslation
    """

    name = 'XWiki Full Page'
    format_id = 'xwiki-fullpage'
    loader = ("properties", "XWikiFullPage")
    language_format = 'java'
