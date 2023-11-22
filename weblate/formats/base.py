# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Base classes for file formats."""

from __future__ import annotations

import os
import tempfile
from copy import copy
from typing import Any, Callable

from django.utils.functional import cached_property
from django.utils.translation import gettext
from weblate_language_data.countries import DEFAULT_LANGS

from weblate.trans.util import get_string
from weblate.utils.errors import add_breadcrumb
from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_TRANSLATED

EXPAND_LANGS = {code[:2]: f"{code[:2]}_{code[3:].upper()}" for code in DEFAULT_LANGS}

ANDROID_CODES = {
    "he": "iw",
    "id": "in",
    "yi": "ji",
}
LEGACY_CODES = {
    "zh_Hans": "zh_CN",
    "zh_Hant": "zh_TW",
    "zh_Hans_SG": "zh_SG",
    "zh_Hant_HK": "zh_HK",
}
APPSTORE_CODES = {
    "ar": "ar-SA",
    "de": "de-DE",
    "fr": "fr-FR",
    "nl": "nl-NL",
    "pt": "pt-PT",
}

# Based on https://support.google.com/googleplay/android-developer/answer/9844778
GOOGLEPLAY_CODES = {
    "hy": "hy-AM",
    "az": "az-AZ",
    "eu": "eu-ES",
    "my": "my-MM",
    "zh_Hant_HK": "zh-HK",
    "zh_Hans": "zh-CN",
    "zh_Hant": "zh-TW",
    "cs": "cs-CZ",
    "da": "da-DK",
    "nl": "nl-NL",
    "en": "en-SG",
    "fi": "fi-FI",
    "fr": "fr-FR",
    "gl": "gl-ES",
    "ka": "ka-GE",
    "de": "de-DE",
    "el": "el-GR",
    "he": "iw-IL",
    "hi": "hi-IN",
    "hu": "hu-HU",
    "is": "is-IS",
    "it": "it-IT",
    "ja": "ja-JP",
    "kn": "kn-IN",
    "km": "km-KH",
    "ko": "ko-KR",
    "ky": "ky-KG",
    "lo": "lo-LA",
    "mk": "mk-MK",
    "ms": "ms-MY",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "mn": "mn-MN",
    "ne": "ne-NP",
    "nb_NO": "no-NO",
    "fa": "fa-IR",
    "pl": "pl-PL",
    "ru": "ru-RU",
    "si": "si-LK",
    "es": "es-ES",
    "sv": "sv-SE",
    "ta": "ta-IN",
    "te": "te-IN",
    "tr": "tr-TR",
}


class UnitNotFoundError(Exception):
    def __str__(self):
        args = list(self.args)
        if "" in args:
            args.remove("")
        return "Unit not found: {}".format(", ".join(args))


class UpdateError(Exception):
    def __init__(self, cmd, output):
        super().__init__(output)
        self.cmd = cmd
        self.output = output


class TranslationUnit:
    """
    Wrapper for translate-toolkit unit.

    It handles ID/template based translations and other API differences.
    """

    id_hash_with_source: bool = False

    def __init__(self, parent, unit, template=None):
        """Create wrapper object."""
        self.unit = unit
        self.template = template
        self.parent = parent
        if template is not None:
            self.mainunit = template
        else:
            self.mainunit = unit

    def _invalidate_target(self):
        """Invalidate target cache."""
        if "target" in self.__dict__:
            del self.__dict__["target"]

    @cached_property
    def locations(self):
        """Return comma separated list of locations."""
        return ""

    @cached_property
    def flags(self):
        """Return flags or typecomments from units."""
        return ""

    @cached_property
    def notes(self):
        """Return notes from units."""
        return ""

    @cached_property
    def source(self):
        """Return source string from a ttkit unit."""
        raise NotImplementedError

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        raise NotImplementedError

    @cached_property
    def explanation(self) -> str:
        """Return explanation from a ttkit unit."""
        return ""

    @cached_property
    def source_explanation(self) -> str:
        """Return source explanation from a ttkit unit."""
        return ""

    @cached_property
    def context(self):
        """
        Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        raise NotImplementedError

    @cached_property
    def previous_source(self):
        """Return previous message source if there was any."""
        return ""

    @classmethod
    def calculate_id_hash(cls, has_template: bool, source: str, context: str):
        """
        Return hash of source string, used for quick lookup.

        We use siphash as it is fast and works well for our purpose.
        """
        if not has_template or cls.id_hash_with_source:
            return calculate_hash(source, context)
        return calculate_hash(context)

    @cached_property
    def id_hash(self):
        return self.calculate_id_hash(
            self.template is not None,
            self.source,
            self.context,
        )

    def is_translated(self):
        """Check whether unit is translated."""
        return bool(self.target)

    def is_approved(self, fallback=False):
        """Check whether unit is approved."""
        return fallback

    def is_fuzzy(self, fallback=False):
        """Check whether unit needs edit."""
        return fallback

    def has_content(self):
        """Check whether unit has content."""
        return True

    def is_readonly(self):
        """Check whether unit is read only."""
        return False

    def set_target(self, target: str | list[str]):
        """Set translation unit target."""
        raise NotImplementedError

    def set_explanation(self, explanation: str):
        return

    def set_source_explanation(self, explanation: str):
        return

    def set_state(self, state):
        """Set fuzzy /approved flag on translated unit."""
        raise NotImplementedError

    def has_unit(self) -> bool:
        return self.unit is not None

    def clone_template(self):
        self.mainunit = self.unit = copy(self.template)
        self._invalidate_target()


class TranslationFormat:
    """Generic object defining file format loader."""

    name: str = ""
    format_id: str = ""
    monolingual: bool | None = None
    check_flags: tuple[str, ...] = ()
    unit_class: type[TranslationUnit] = TranslationUnit
    autoload: tuple[str, ...] = ()
    can_add_unit: bool = True
    can_delete_unit: bool = True
    language_format: str = "posix"
    simple_filename: bool = True
    new_translation: str | bytes | None = None
    autoaddon: dict[str, dict[str, str]] = {}
    create_empty_bilingual: bool = False
    bilingual_class = None
    create_style = "create"
    has_multiple_strings: bool = False
    supports_explanation: bool = False
    can_edit_base: bool = True
    strict_format_plurals: bool = False
    plural_preference: tuple[int, ...] | None = None

    @classmethod
    def get_identifier(cls):
        return cls.format_id

    @classmethod
    def parse(
        cls,
        storefile,
        template_store=None,
        language_code: str | None = None,
        source_language: str | None = None,
        is_template: bool = False,
        existing_units: list[Any] | None = None,
    ):
        """
        Parse store and returns TranslationFormat instance.

        This wrapper is needed for AutodetectFormat to be able to return instance of
        different class.
        """
        return cls(
            storefile,
            template_store=template_store,
            language_code=language_code,
            source_language=source_language,
            is_template=is_template,
            existing_units=existing_units,
        )

    def __init__(
        self,
        storefile,
        template_store=None,
        language_code: str | None = None,
        source_language: str | None = None,
        is_template: bool = False,
        existing_units: list[Any] | None = None,
    ):
        """Create file format object, wrapping up translate-toolkit's store."""
        if not isinstance(storefile, str) and not hasattr(storefile, "mode"):
            storefile.mode = "r"

        self.storefile = storefile
        self.language_code = language_code
        self.source_language = source_language
        # Remember template
        self.template_store = template_store
        self.is_template = is_template
        self.existing_units = [] if existing_units is None else existing_units

        # Load store
        self.store = self.load(storefile, template_store)

        self.add_breadcrumb(
            "Loaded translation file {}".format(
                getattr(storefile, "filename", storefile)
            ),
            template_store=str(template_store),
            is_template=is_template,
        )

    def _invalidate_units(self):
        for key in ("all_units", "template_units", "_unit_index", "_template_index"):
            if key in self.__dict__:
                del self.__dict__[key]

    def check_valid(self):
        """Check store validity."""
        if not self.is_valid():
            raise ValueError(
                gettext(
                    "Could not load strings from the file, try choosing other format."
                )
            )
        self.ensure_index()

    def get_filenames(self):
        if isinstance(self.storefile, str):
            return [self.storefile]
        return [self.storefile.name]

    def load(self, storefile, template_store):
        raise NotImplementedError

    @classmethod
    def get_plural(cls, language, store=None):  # noqa: ARG003
        """Return matching plural object."""
        if cls.plural_preference is not None:
            # Fetch all matching plurals
            plurals = language.plural_set.filter(source__in=cls.plural_preference)

            # Use first matching in the order of preference
            for source in cls.plural_preference:
                for plural in plurals:
                    if plural.source == source:
                        return plural

        # Fall back to default one
        return language.plural

    @cached_property
    def has_template(self):
        """Check whether class is using template."""
        return (
            self.monolingual or self.monolingual is None
        ) and self.template_store is not None

    @cached_property
    def _template_index(self):
        """ID based index for units."""
        return {unit.id_hash: unit for unit in self.template_units}

    def find_unit_template(
        self, context: str, source: str, id_hash: int | None = None
    ) -> Any | None:
        if id_hash is None:
            id_hash = self._calculate_string_hash(context, source)
        try:
            # The mono units always have only template set
            return self._template_index[id_hash].template
        except KeyError:
            return None

    def _find_unit_monolingual(self, context: str, source: str) -> tuple[Any, bool]:
        # We search by ID when using template
        id_hash = self._calculate_string_hash(context, source)
        try:
            result = self._unit_index[id_hash]
        except KeyError:
            raise UnitNotFoundError(context, source)

        add = False
        if not result.has_unit():
            # We always need copy of template unit to translate
            result.clone_template()
            add = True
        return result, add

    @cached_property
    def _unit_index(self):
        """Context and source based index for units."""
        return {unit.id_hash: unit for unit in self.content_units}

    def _calculate_string_hash(self, context: str, source: str) -> int:
        """Calculates id hash for a string."""
        return self.unit_class.calculate_id_hash(
            self.has_template or self.is_template, get_string(source), context
        )

    def _find_unit_bilingual(self, context: str, source: str) -> tuple[Any, bool]:
        id_hash = self._calculate_string_hash(context, source)
        try:
            return (self._unit_index[id_hash], False)
        except KeyError:
            raise UnitNotFoundError(context, source)

    def find_unit(self, context: str, source: str | None = None) -> tuple[Any, bool]:
        """
        Find unit by context and source.

        Returns tuple (ttkit_unit, created) indicating whether returned unit is new one.
        """
        if self.has_template:
            return self._find_unit_monolingual(context, source)
        return self._find_unit_bilingual(context, source)

    def ensure_index(self):
        return self._unit_index

    def add_unit(self, ttkit_unit):
        """Add new unit to underlying store."""
        raise NotImplementedError

    def update_header(self, **kwargs):
        """Update store header if available."""
        return

    @staticmethod
    def save_atomic(filename, callback):
        dirname, basename = os.path.split(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        temp = tempfile.NamedTemporaryFile(prefix=basename, dir=dirname, delete=False)
        try:
            callback(temp)
            temp.close()
            os.replace(temp.name, filename)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)

    def save(self):
        """Save underlying store to disk."""
        raise NotImplementedError

    @property
    def all_store_units(self):
        """Wrapper for all store units for possible filtering."""
        return self.store.units

    @cached_property
    def template_units(self):
        return [self.unit_class(self, None, unit) for unit in self.all_store_units]

    def _get_all_bilingual_units(self):
        return [self.unit_class(self, unit) for unit in self.all_store_units]

    def _build_monolingual_unit(self, unit):
        return self.unit_class(
            self,
            self.find_unit_template(unit.context, unit.source, unit.id_hash),
            unit.template,
        )

    def _get_all_monolingual_units(self):
        return [
            self._build_monolingual_unit(unit)
            for unit in self.template_store.template_units
        ]

    @cached_property
    def all_units(self):
        """List of all units."""
        if not self.has_template:
            return self._get_all_bilingual_units()
        return self._get_all_monolingual_units()

    @property
    def content_units(self):
        return [unit for unit in self.all_units if unit.has_content()]

    @staticmethod
    def mimetype():
        """Return most common mime type for format."""
        return "text/plain"

    @staticmethod
    def extension():
        """Return most common file extension for format."""
        return "txt"

    def is_valid(self):
        """Check whether store seems to be valid."""
        for unit in self.content_units:
            # Just make sure that id_hash can be calculated
            unit.id_hash  # noqa: B018
        return True

    @classmethod
    def is_valid_base_for_new(
        cls,
        base: str,
        monolingual: bool,
        errors: list | None = None,
        fast: bool = False,
    ) -> bool:
        """Check whether base is valid."""
        raise NotImplementedError

    @classmethod
    def get_language_code(cls, code: str, language_format: str | None = None) -> str:
        """Do any possible formatting needed for language code."""
        if not language_format:
            language_format = cls.language_format
        return getattr(cls, f"get_language_{language_format}")(code)

    @staticmethod
    def get_language_posix(code: str) -> str:
        return code.replace("-", "_")

    @staticmethod
    def get_language_bcp(code: str) -> str:
        return code.replace("_", "-")

    @classmethod
    def get_language_bcp_lower(cls, code: str) -> str:
        return cls.get_language_bcp(code).lower()

    @classmethod
    def get_language_posix_long(cls, code: str) -> str:
        return EXPAND_LANGS.get(code, cls.get_language_posix(code))

    @classmethod
    def get_language_posix_long_lowercase(cls, code: str) -> str:
        return EXPAND_LANGS.get(code, cls.get_language_posix(code)).lower()

    @classmethod
    def get_language_linux(cls, code: str) -> str:
        """Linux doesn't use Hans/Hant, but rather TW/CN variants."""
        return LEGACY_CODES.get(code, cls.get_language_posix(code))

    @classmethod
    def get_language_bcp_long(cls, code: str) -> str:
        return cls.get_language_bcp(cls.get_language_posix_long(code))

    @classmethod
    def get_language_android(cls, code: str) -> str:
        """Android doesn't use Hans/Hant, but rather TW/CN variants."""
        # Exceptions
        if code in ANDROID_CODES:
            return ANDROID_CODES[code]

        # Base on Java
        sanitized = cls.get_language_linux(code)

        # Handle variants
        if "_" in sanitized and len(sanitized.split("_")[1]) > 2:
            return "b+{}".format(sanitized.replace("_", "+"))

        # Handle countries
        return sanitized.replace("_", "-r")

    @classmethod
    def get_language_bcp_legacy(cls, code: str) -> str:
        """BCP, but doesn't use Hans/Hant, but rather TW/CN variants."""
        return cls.get_language_bcp(cls.get_language_linux(code))

    @classmethod
    def get_language_appstore(cls, code: str) -> str:
        """Apple App Store language codes."""
        return cls.get_language_bcp(APPSTORE_CODES.get(code, code))

    @classmethod
    def get_language_googleplay(cls, code: str) -> str:
        """Google Play language codes."""
        return cls.get_language_bcp(GOOGLEPLAY_CODES.get(code, code))

    @classmethod
    def get_language_filename(cls, mask: str, code: str) -> str:
        """
        Returns full filename of a language file.

        Calculated for given path, filemask and language code.
        """
        return mask.replace("*", code)

    @classmethod
    def add_language(
        cls,
        filename: str,
        language: str,
        base: str,
        callback: Callable | None = None,
    ):
        """Add new language file."""
        # Create directory for a translation
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cls.create_new_file(filename, language, base, callback)

    @classmethod
    def get_new_file_content(cls):
        return None

    @classmethod
    def create_new_file(
        cls,
        filename: str,
        language: str,
        base: str,
        callback: Callable | None = None,
    ):
        """Handle creation of new translation file."""
        raise NotImplementedError

    def iterate_merge(self, fuzzy: str, only_translated: bool = True):
        """
        Iterate over units for merging.

        Note: This can change fuzzy state of units!
        """
        for unit in self.content_units:
            # Skip fuzzy (if asked for that)
            if unit.is_fuzzy():
                if not fuzzy:
                    continue
            elif only_translated and not unit.is_translated():
                continue

            # Unmark unit as fuzzy (to allow merge)
            set_fuzzy = False
            if fuzzy and unit.is_fuzzy():
                unit.set_state(STATE_TRANSLATED)
                if fuzzy != "approve":
                    set_fuzzy = True

            yield set_fuzzy, unit

    def create_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ):
        raise NotImplementedError

    def new_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
        skip_build: bool = False,
    ):
        """Add new unit to monolingual store."""
        # Create backend unit object
        unit = self.create_unit(key, source, target)

        # Add it to the file
        self.add_unit(unit)

        if skip_build:
            return None

        # Build an unit object
        if self.has_template:
            if self.is_template:
                template_unit = unit
            else:
                template_unit = self._find_unit_monolingual(key, source)
        else:
            template_unit = None
        result = self.unit_class(self, unit, template_unit)
        mono_unit = self.unit_class(self, None, unit)

        # Update cached lookups
        if "all_units" in self.__dict__:
            self.all_units.append(result)
        if "template_units" in self.__dict__:
            self.template_units.append(mono_unit)
        if "_unit_index" in self.__dict__:
            self._unit_index[result.id_hash] = result
        if "_template_index" in self.__dict__:
            self._template_index[mono_unit.id_hash] = mono_unit

        return result

    @classmethod
    def get_class(cls):
        raise NotImplementedError

    @classmethod
    def add_breadcrumb(cls, message, **data):
        add_breadcrumb(category="storage", message=message, **data)

    def delete_unit(self, ttkit_unit) -> str | None:
        raise NotImplementedError

    def cleanup_unused(self) -> list[str] | None:
        """Removes unused strings, returning list of additional changed files."""
        if not self.template_store:
            return None
        existing = {template.context for template in self.template_store.template_units}

        changed = False
        needs_save = False
        result = []

        # Iterate over copy of a list as we are changing it when removing units
        for unit in list(self.all_store_units):
            if self.unit_class(self, None, unit).context not in existing:
                changed = True
                item = self.delete_unit(unit)
                if item is not None:
                    result.append(item)
                else:
                    needs_save = True

        if not changed:
            return None

        if needs_save:
            self.save()
        self._invalidate_units()
        return result

    def cleanup_blank(self) -> list[str]:
        """
        Removes strings without translations.

        Returning list of additional changed files.
        """
        changed = False
        needs_save = False
        result = []

        # Iterate over copy of a list as we are changing it when removing units
        for ttkit_unit in list(self.all_store_units):
            target = self.unit_class(self, ttkit_unit, ttkit_unit).target
            if not target or (isinstance(target, list) and not any(target)):
                changed = True
                item = self.delete_unit(ttkit_unit)
                if item is not None:
                    result.append(item)
                else:
                    needs_save = True

        if not changed:
            return None

        if needs_save:
            self.save()
        self._invalidate_units()
        return result

    def remove_unit(self, ttkit_unit) -> list[str]:
        """High level wrapper for unit removal."""
        changed = False

        result = []

        item = self.delete_unit(ttkit_unit)
        if item is not None:
            result.append(item)
        else:
            changed = True

        if changed:
            self.save()
        self._invalidate_units()
        return result

    @staticmethod
    def validate_context(context: str):  # noqa: ARG004
        return


class EmptyFormat(TranslationFormat):
    """For testing purposes."""

    @classmethod
    def load(cls, storefile, template_store):  # noqa: ARG003
        return type("", (object,), {"units": []})()

    def save(self):
        return


class BilingualUpdateMixin:
    @classmethod
    def do_bilingual_update(cls, in_file: str, out_file: str, template: str, **kwargs):
        raise NotImplementedError

    @classmethod
    def update_bilingual(cls, filename: str, template: str, **kwargs):
        temp = tempfile.NamedTemporaryFile(
            prefix=filename, dir=os.path.dirname(filename), delete=False
        )
        temp.close()
        try:
            cls.do_bilingual_update(filename, temp.name, template, **kwargs)
            os.replace(temp.name, filename)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)
