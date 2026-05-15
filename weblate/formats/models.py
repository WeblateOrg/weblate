# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from appconf import AppConf
from django.utils.functional import cached_property

from weblate.utils.classloader import ClassLoader

from .base import BaseExporter, TranslationFormat
from .defaults import DEFAULT_FORMATS


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
        "weblate.formats.exporters.MultiCSVExporter",
        "weblate.formats.exporters.XlsxExporter",
        "weblate.formats.exporters.JSONExporter",
        "weblate.formats.exporters.JSONNestedExporter",
        "weblate.formats.exporters.AndroidResourceExporter",
        "weblate.formats.exporters.StringsExporter",
    )

    FORMATS = DEFAULT_FORMATS

    class Meta:
        prefix = "WEBLATE"
