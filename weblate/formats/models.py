# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from appconf import AppConf
from django.utils.functional import cached_property

from weblate.utils.classloader import ClassLoader

from .base import BaseExporter, TranslationFormat


class ExporterLoader(ClassLoader):
    def __init__(self) -> None:
        super().__init__("WEBLATE_EXPORTERS", construct=False, base_class=BaseExporter)

    def list_exporters(self, translation):
        return [
            {"name": x.name, "verbose": x.verbose}
            for x in sorted(self.values(), key=lambda x: x.name)
            if x.supports(translation)
        ]

    def list_exporters_filter(self, allowed):
        return [
            {"name": x.name, "verbose": x.verbose}
            for x in sorted(self.values(), key=lambda x: x.name)
            if x.name in allowed
        ]


EXPORTERS = ExporterLoader()


class FileFormatLoader(ClassLoader):
    def __init__(self) -> None:
        super().__init__(
            "WEBLATE_FORMATS", construct=False, base_class=TranslationFormat
        )
        self.errors = {}

    @cached_property
    def autoload(self):
        return [
            (autoload, fileformat)
            for fileformat in self.data.values()
            for autoload in fileformat.autoload
        ]

    def get_settings(self):
        result = list(super().get_settings())
        # TBX is required for glossaries
        if "weblate.formats.ttkit.TBXFormat" not in result:
            result.append("weblate.formats.ttkit.TBXFormat")
        return result


FILE_FORMATS = FileFormatLoader()


class FormatsConf(AppConf):
    EXPORTERS = (
        "weblate.formats.exporters.PoExporter",
        "weblate.formats.exporters.PoXliffExporter",
        "weblate.formats.exporters.XliffExporter",
        "weblate.formats.exporters.TBXExporter",
        "weblate.formats.exporters.TMXExporter",
        "weblate.formats.exporters.MoExporter",
        "weblate.formats.exporters.CSVExporter",
        "weblate.formats.exporters.XlsxExporter",
        "weblate.formats.exporters.JSONExporter",
        "weblate.formats.exporters.JSONNestedExporter",
        "weblate.formats.exporters.AndroidResourceExporter",
        "weblate.formats.exporters.StringsExporter",
    )

    FORMATS = (
        "weblate.formats.ttkit.PoFormat",
        "weblate.formats.ttkit.PoMonoFormat",
        "weblate.formats.ttkit.TSFormat",
        "weblate.formats.ttkit.XliffFormat",
        "weblate.formats.ttkit.RichXliffFormat",
        "weblate.formats.ttkit.PoXliffFormat",
        "weblate.formats.ttkit.StringsFormat",
        "weblate.formats.ttkit.StringsUtf8Format",
        "weblate.formats.ttkit.PropertiesUtf8Format",
        "weblate.formats.ttkit.PropertiesUtf16Format",
        "weblate.formats.ttkit.PropertiesFormat",
        "weblate.formats.ttkit.JoomlaFormat",
        "weblate.formats.ttkit.GWTFormat",
        "weblate.formats.ttkit.GWTISOFormat",
        "weblate.formats.ttkit.PhpFormat",
        "weblate.formats.ttkit.LaravelPhpFormat",
        "weblate.formats.ttkit.RESXFormat",
        "weblate.formats.ttkit.AndroidFormat",
        "weblate.formats.ttkit.MOKOFormat",
        "weblate.formats.ttkit.JSONFormat",
        "weblate.formats.ttkit.JSONNestedFormat",
        "weblate.formats.ttkit.WebExtensionJSONFormat",
        "weblate.formats.ttkit.I18NextFormat",
        "weblate.formats.ttkit.I18NextV4Format",
        "weblate.formats.ttkit.GoI18JSONFormat",
        "weblate.formats.ttkit.GoI18V2JSONFormat",
        "weblate.formats.ttkit.GoTextFormat",
        "weblate.formats.ttkit.ARBFormat",
        "weblate.formats.ttkit.FormatJSFormat",
        "weblate.formats.ttkit.CSVFormat",
        "weblate.formats.ttkit.CSVUtf8Format",
        "weblate.formats.ttkit.CSVSimpleFormat",
        "weblate.formats.ttkit.CSVUtf8SimpleFormat",
        "weblate.formats.ttkit.CSVSimpleFormatISO",
        "weblate.formats.ttkit.YAMLFormat",
        "weblate.formats.ttkit.RubyYAMLFormat",
        "weblate.formats.ttkit.SubRipFormat",
        "weblate.formats.ttkit.MicroDVDFormat",
        "weblate.formats.ttkit.AdvSubStationAlphaFormat",
        "weblate.formats.ttkit.SubStationAlphaFormat",
        "weblate.formats.ttkit.DTDFormat",
        "weblate.formats.ttkit.FlatXMLFormat",
        "weblate.formats.ttkit.ResourceDictionaryFormat",
        "weblate.formats.ttkit.INIFormat",
        "weblate.formats.ttkit.InnoSetupINIFormat",
        "weblate.formats.ttkit.PropertiesMi18nFormat",
        "weblate.formats.external.XlsxFormat",
        "weblate.formats.txt.AppStoreFormat",
        "weblate.formats.convert.HTMLFormat",
        "weblate.formats.convert.IDMLFormat",
        "weblate.formats.convert.OpenDocumentFormat",
        "weblate.formats.convert.PlainTextFormat",
        "weblate.formats.convert.DokuWikiFormat",
        "weblate.formats.convert.MarkdownFormat",
        "weblate.formats.convert.MediaWikiFormat",
        "weblate.formats.convert.WindowsRCFormat",
        "weblate.formats.ttkit.XWikiPropertiesFormat",
        "weblate.formats.ttkit.XWikiPagePropertiesFormat",
        "weblate.formats.ttkit.XWikiFullPageFormat",
        "weblate.formats.ttkit.TBXFormat",
        "weblate.formats.ttkit.StringsdictFormat",
        "weblate.formats.ttkit.FluentFormat",
        "weblate.formats.multi.MultiCSVUtf8Format",
    )

    class Meta:
        prefix = "WEBLATE"
