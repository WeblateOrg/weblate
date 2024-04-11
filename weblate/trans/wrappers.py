# Copyright © Michal Karol <m.karol@neurosys.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from translate.storage.base import DictStore

from weblate.formats.base import TranslationFormat
from weblate.formats.exporters import BaseExporter, JSONExporter
from weblate.formats.ttkit import JSONFormat
from weblate.trans.defines import DEFAULT_KEY_SEPARATOR


def store_class_custom_key_separator_wrapper(store_cls: DictStore, key_separator: str):
    """Create class deriving from store class with overridden key separator."""

    class CustomKeySeparatorUnitIdClass(store_cls.UnitClass.IdClass):
        """IdClass with overridden key separator."""

        KEY_SEPARATOR = key_separator

    class CustomKeySeparatorStoreUnitClass(store_cls.UnitClass):
        """UnitClass with overridden IdClass."""

        IdClass = CustomKeySeparatorUnitIdClass

    class CustomKeySeparatorStoreClass(store_cls):
        """StoreClass with overridden UnitClass."""

        UnitClass = CustomKeySeparatorStoreUnitClass

    return CustomKeySeparatorStoreClass


def file_format_custom_key_separator_wrapper(
    file_format_cls: type[TranslationFormat], key_separator: str
):
    """Create class deriving from file format class with overridden key separator if file format class derives from JSONFormat."""
    if (
        not issubclass(file_format_cls, JSONFormat)
        or key_separator == DEFAULT_KEY_SEPARATOR
    ):
        return file_format_cls

    class CustomKeySeparatorUnitClass(file_format_cls.unit_class):
        """File format unit class with overridden custom key separator."""

        KEY_SEPARATOR = key_separator

    class CustomKeySeparatorFileFormat(file_format_cls):
        """File format class with overridden loader and unit class to a classes with overridden custom key separator."""

        loader = store_class_custom_key_separator_wrapper(
            file_format_cls.get_class(), key_separator
        )
        unit_class = CustomKeySeparatorUnitClass

    return CustomKeySeparatorFileFormat


def exporter_custom_key_separator_wrapper(
    exporter_cls: type[BaseExporter], key_separator: str
):
    """Create class deriving from exporter class with overridden key separator if exporter class derives from JSONExporter."""
    if (
        not issubclass(exporter_cls, JSONExporter)
        or key_separator == DEFAULT_KEY_SEPARATOR
    ):
        return exporter_cls

    class CustomKeyExporter(exporter_cls):
        """Exporter class with overridden storage_class to a class with overridden custom key separator."""

        storage_class = store_class_custom_key_separator_wrapper(
            exporter_cls.storage_class, key_separator
        )

    return CustomKeyExporter
