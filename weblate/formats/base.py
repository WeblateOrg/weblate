# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Base classes for file formats."""

from __future__ import annotations

import os
import tempfile
from copy import copy
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, ClassVar, TypeAlias

from django.http import HttpResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext
from translate.misc.multistring import multistring
from translate.storage.base import TranslationStore as TranslateToolkitStore
from translate.storage.base import TranslationUnit as TranslateToolkitUnit
from weblate_language_data.countries import DEFAULT_LANGS

from weblate.trans.util import get_string, join_plural, split_plural
from weblate.utils.errors import add_breadcrumb
from weblate.utils.hash import calculate_hash
from weblate.utils.site import get_site_url
from weblate.utils.state import STATE_EMPTY, STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from django_stubs_ext import StrOrPromise

    from weblate.trans.models import Unit


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
    "te": "te-IN",  # codespell:ignore te
    "tr": "tr-TR",
}


class UnitNotFoundError(Exception):
    def __str__(self) -> str:
        args = list(self.args)
        if "" in args:
            args.remove("")
        return "Unit not found: {}".format(", ".join(args))


class UpdateError(Exception):
    def __init__(self, cmd, output) -> None:
        super().__init__(output)
        self.cmd = cmd
        self.output = output


class MissingTemplateError(TypeError):
    pass


class BaseItem:
    pass


InnerUnit: TypeAlias = TranslateToolkitUnit | BaseItem


class BaseStore:
    units: Sequence[InnerUnit]


InnerStore: TypeAlias = TranslateToolkitStore | BaseStore


class TranslationUnit:
    """
    Wrapper for translate-toolkit unit.

    It handles ID/template based translations and other API differences.
    """

    id_hash_with_source: bool = False
    template: InnerUnit | None
    unit: InnerUnit | None
    parent: TranslationFormat
    mainunit: InnerUnit
    empty_unit_ok: ClassVar[bool] = False

    def __init__(
        self,
        parent: TranslationFormat,
        unit: InnerUnit | None,
        template: InnerUnit | None = None,
    ) -> None:
        """Create wrapper object."""
        self.unit = unit
        self.template = template
        self.parent = parent
        if template is not None:
            self.mainunit = template
        elif unit is None and not self.empty_unit_ok:
            # MultiUnit is just wrapper around more unit objects, does not have
            # actual main unit
            raise MissingTemplateError
        else:
            self.mainunit = unit

    def _invalidate_target(self) -> None:
        """Invalidate target cache."""
        if "target" in self.__dict__:
            del self.__dict__["target"]

    def invalidate_all_caches(self) -> None:
        """Invalidate attributes cache."""
        for attr in (
            "context",
            "source",
            "locations",
            "flags",
            "notes",
            "explanation",
            "source_explanation",
            "previous_source",
        ):
            if attr in self.__dict__:
                del self.__dict__[attr]
        self._invalidate_target()

    @cached_property
    def locations(self) -> str:
        """Return comma separated list of locations."""
        return ""

    @cached_property
    def flags(self) -> str:
        """Return flags or typecomments from units."""
        return ""

    @cached_property
    def notes(self) -> str:
        """Return notes from units."""
        return ""

    @cached_property
    def source(self) -> str:
        """Return source string from a ttkit unit."""
        raise NotImplementedError

    @cached_property
    def target(self) -> str:
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
    def context(self) -> str:
        """
        Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        raise NotImplementedError

    @cached_property
    def previous_source(self) -> str:
        """Return previous message source if there was any."""
        return ""

    @classmethod
    def calculate_id_hash(cls, has_template: bool, source: str, context: str) -> int:
        """
        Return hash of source string, used for quick lookup.

        We use siphash as it is fast and works well for our purpose.
        """
        if not has_template or cls.id_hash_with_source:
            return calculate_hash(source, context)
        return calculate_hash(context)

    @cached_property
    def id_hash(self) -> int:
        return self.calculate_id_hash(
            self.template is not None,
            self.source,
            self.context,
        )

    def has_translation(self) -> bool:
        """Check whether unit has translation."""
        return any(split_plural(self.target))

    def is_translated(self) -> bool:
        """Check whether unit is translated."""
        return self.has_translation()

    def is_approved(self, fallback=False) -> bool:
        """Check whether unit is approved."""
        return fallback

    def is_fuzzy(self, fallback=False) -> bool:
        """Check whether unit needs edit."""
        return fallback

    def has_content(self) -> bool:
        """Check whether unit has content."""
        return True

    def is_readonly(self) -> bool:
        """Check whether unit is read-only."""
        return False

    def set_target(self, target: str | list[str]) -> None:
        """Set translation unit target."""
        raise NotImplementedError

    def set_explanation(self, explanation: str) -> None:
        return

    def set_source_explanation(self, explanation: str) -> None:
        return

    def set_state(self, state) -> None:
        """Set fuzzy /approved flag on translated unit."""
        raise NotImplementedError

    def has_unit(self) -> bool:
        return self.unit is not None

    def clone_template(self) -> None:
        if self.template is None:
            raise MissingTemplateError
        self.mainunit = self.unit = copy(self.template)
        self._invalidate_target()

    def untranslate(self, language) -> None:
        self.set_target("")
        self.set_state(STATE_EMPTY)


class TranslationFormat:
    """Generic object defining file format loader."""

    name: StrOrPromise = ""
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
    bilingual_class: type[TranslationFormat] | None = None
    create_style = "create"
    has_multiple_strings: bool = False
    supports_explanation: bool = False
    supports_plural: bool = False
    can_edit_base: bool = True
    strict_format_plurals: bool = False
    plural_preference: tuple[int, ...] | None = None
    store: InnerStore

    @classmethod
    def get_identifier(cls):
        return cls.format_id

    def __init__(
        self,
        storefile: Path | str | BinaryIO,
        template_store: TranslationFormat | None = None,
        language_code: str | None = None,
        source_language: str | None = None,
        is_template: bool = False,
        existing_units: list[Unit] | None = None,
    ) -> None:
        """Create file format object, wrapping up translate-toolkit's store."""
        if isinstance(storefile, Path):
            storefile = str(storefile.as_posix())
        if not isinstance(storefile, str) and not hasattr(storefile, "mode"):
            # This is BinaryIO like but without a mode
            storefile.mode = "r"  # type: ignore[misc]

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

    def _invalidate_units(self) -> None:
        for key in ("all_units", "template_units", "_unit_index", "_template_index"):
            if key in self.__dict__:
                del self.__dict__[key]

    def check_valid(self) -> None:
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

    def load(
        self, storefile: str | BinaryIO, template_store: TranslationFormat | None
    ) -> InnerStore:
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
    ) -> InnerUnit | None:
        if id_hash is None:
            id_hash = self._calculate_string_hash(context, source)
        try:
            # The mono units always have only template set
            return self._template_index[id_hash].template
        except KeyError:
            return None

    def _find_unit_monolingual(
        self, context: str, source: str
    ) -> tuple[TranslationUnit, bool]:
        # We search by ID when using template
        id_hash = self._calculate_string_hash(context, source)
        try:
            result = self._unit_index[id_hash]
        except KeyError as error:
            raise UnitNotFoundError(context, source) from error

        add = False
        if not result.has_unit():
            # We always need copy of template unit to translate
            result.clone_template()
            add = True
        return result, add

    @cached_property
    def _unit_index(self) -> dict[int, TranslationUnit]:
        """Context and source based index for units."""
        return {unit.id_hash: unit for unit in self.content_units}

    def _calculate_string_hash(self, context: str, source: str) -> int:
        """Calculate id hash for a string."""
        return self.unit_class.calculate_id_hash(
            self.has_template or self.is_template, get_string(source), context
        )

    def _find_unit_bilingual(
        self, context: str, source: str
    ) -> tuple[TranslationUnit, bool]:
        id_hash = self._calculate_string_hash(context, source)
        try:
            return (self._unit_index[id_hash], False)
        except KeyError as error:
            raise UnitNotFoundError(context, source) from error

    def find_unit(self, context: str, source: str) -> tuple[TranslationUnit, bool]:
        """
        Find unit by context and source.

        Returns tuple (ttkit_unit, created) indicating whether returned unit is new one.
        """
        if self.has_template:
            return self._find_unit_monolingual(context, source)
        return self._find_unit_bilingual(context, source)

    def ensure_index(self):
        return self._unit_index

    def add_unit(self, unit: TranslationUnit) -> None:
        """Add new unit to underlying store."""
        raise NotImplementedError

    def update_header(self, **kwargs) -> None:
        """Update store header if available."""
        return

    @staticmethod
    def save_atomic(filename, callback) -> None:
        dirname, basename = os.path.split(filename)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        try:
            with tempfile.NamedTemporaryFile(
                prefix=basename, dir=dirname, delete=False
            ) as temp:
                callback(temp)
            os.replace(temp.name, filename)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)

    def save(self) -> None:
        """Save underlying store to disk."""
        raise NotImplementedError

    @property
    def all_store_units(self) -> list[InnerUnit]:
        """Wrapper for all store units for possible filtering."""
        return self.store.units  # type: ignore[return-value]

    @cached_property
    def template_units(self) -> list[TranslationUnit]:
        return [self.unit_class(self, None, unit) for unit in self.all_store_units]

    def _get_all_bilingual_units(self) -> list[TranslationUnit]:
        return [self.unit_class(self, unit) for unit in self.all_store_units]

    def _build_monolingual_unit(self, unit: TranslationUnit) -> TranslationUnit:
        return self.unit_class(
            self,
            self.find_unit_template(unit.context, unit.source, unit.id_hash),
            unit.template,
        )

    def _get_all_monolingual_units(self) -> list[TranslationUnit]:
        if self.template_store is None:
            raise MissingTemplateError
        return [
            self._build_monolingual_unit(unit)
            for unit in self.template_store.template_units
        ]

    @cached_property
    def all_units(self) -> list[TranslationUnit]:
        """List of all units."""
        if not self.has_template:
            return self._get_all_bilingual_units()
        return self._get_all_monolingual_units()

    @property
    def content_units(self) -> list[TranslationUnit]:
        return [unit for unit in self.all_units if unit.has_content()]

    @staticmethod
    def mimetype() -> str:
        """Return most common mime type for format."""
        return "text/plain"

    @staticmethod
    def extension() -> str:
        """Return most common file extension for format."""
        return "txt"

    def is_valid(self) -> bool:
        """Check whether store seems to be valid."""
        for unit in self.content_units:
            # Just ensure that id_hash can be calculated
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

    @classmethod
    def get_language_posix_lowercase(cls, code: str) -> str:
        return cls.get_language_posix(code).lower()

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
    def get_language_linux_lowercase(cls, code: str) -> str:
        return cls.get_language_linux(code).lower()

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
        Return  full filename of a language file.

        Calculated for given path, filemask and language code.
        """
        return mask.replace("*", code)

    @classmethod
    def add_language(
        cls,
        filename: str | Path,
        language: str,
        base: str,
        callback: Callable | None = None,
    ) -> None:
        """Add new language file."""
        # Create directory for a translation
        if not isinstance(filename, Path):
            filename = Path(filename)
        dirname = filename.parent
        if not dirname.exists():
            dirname.mkdir(parents=True)

        cls.create_new_file(str(filename.as_posix()), language, base, callback)

    @classmethod
    def get_new_file_content(cls) -> bytes:
        return b""

    @classmethod
    def create_new_file(
        cls,
        filename: str,
        language: str,
        base: str,
        callback: Callable | None = None,
    ) -> None:
        """Handle creation of new translation file."""
        raise NotImplementedError

    def iterate_merge(
        self, fuzzy: str, only_translated: bool = True
    ) -> Iterator[tuple[bool, TranslationUnit]]:
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
    ) -> InnerUnit:
        raise NotImplementedError

    def new_unit(
        self,
        key: str,
        source: str | list[str],
        target: str | list[str] | None = None,
    ) -> TranslationUnit:
        """Add new unit to monolingual store."""
        # Create backend unit object
        unit = self.create_unit(key, source, target)

        # Build an unit object
        template_unit: InnerUnit | None
        if self.has_template:
            if self.is_template:
                template_unit = unit
            else:
                template_unit = self._find_unit_monolingual(
                    key, join_plural(source) if isinstance(source, list) else source
                )[0].unit
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

        # Add it to the file
        self.add_unit(result)

        # Invalidate all attributes
        result.invalidate_all_caches()

        return result

    @classmethod
    def get_class(cls) -> InnerStore | None:
        raise NotImplementedError

    @classmethod
    def add_breadcrumb(cls, message, **data) -> None:
        add_breadcrumb(category="storage", message=message, **data)

    def delete_unit(self, ttkit_unit: InnerUnit) -> str | None:
        raise NotImplementedError

    def cleanup_unused(self) -> list[str] | None:
        """Remove unused strings, returning list of additional changed files."""
        if not self.template_store or not self.can_delete_unit:
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

    def cleanup_blank(self) -> list[str] | None:
        """
        Remove strings without translations.

        Returning list of additional changed files.
        """
        if not self.can_delete_unit:
            return None
        changed = False
        needs_save = False
        result = []

        # Iterate over copy of a list as we are changing it when removing units
        for ttkit_unit in list(self.all_store_units):
            target = split_plural(self.unit_class(self, ttkit_unit, ttkit_unit).target)
            if not any(target):
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

    def remove_unit(self, ttkit_unit: InnerUnit) -> list[str]:
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
    def validate_context(context: str) -> None:  # noqa: ARG004
        return


class EmptyFormat(TranslationFormat):
    """For testing purposes."""

    @classmethod
    def load(cls, storefile, template_store):  # noqa: ARG003
        return type("", (object,), {"units": []})()

    def save(self) -> None:
        return


class BilingualUpdateMixin:
    @classmethod
    def do_bilingual_update(
        cls, in_file: str, out_file: str, template: str, **kwargs
    ) -> None:
        raise NotImplementedError

    @classmethod
    def update_bilingual(cls, filename: str, template: str, **kwargs) -> None:
        with tempfile.NamedTemporaryFile(
            prefix=filename, dir=os.path.dirname(filename), delete=False
        ) as temp:
            # We want file to be created only here
            pass
        try:
            cls.do_bilingual_update(filename, temp.name, template, **kwargs)
            os.replace(temp.name, filename)
        finally:
            if os.path.exists(temp.name):
                os.unlink(temp.name)


class BaseExporter:
    content_type = "text/plain"
    extension = "txt"
    name = ""
    verbose: StrOrPromise = ""
    set_id = False
    storage_class: ClassVar[type[TranslateToolkitStore]]

    def __init__(
        self,
        project=None,
        source_language=None,
        language=None,
        url=None,
        translation=None,
        fieldnames=None,
    ) -> None:
        self.translation = translation
        if translation is not None:
            self.plural = translation.plural
            self.project = translation.component.project
            self.source_language = translation.component.source_language
            self.language = translation.language
            self.url = get_site_url(translation.get_absolute_url())
        else:
            self.project = project
            self.language = language
            self.source_language = source_language
            self.plural = language.plural
            self.url = url
        self.fieldnames = fieldnames

    @staticmethod
    def supports(translation) -> bool:  # noqa: ARG004
        return True

    @cached_property
    def storage(self):
        storage = self.get_storage()
        storage.setsourcelanguage(self.source_language.code)
        storage.settargetlanguage(self.language.code)
        return storage

    def string_filter(self, text):
        return text

    def handle_plurals(self, plurals):
        if len(plurals) == 1:
            return self.string_filter(plurals[0])
        return multistring([self.string_filter(plural) for plural in plurals])

    @classmethod
    def get_identifier(cls):
        return cls.name

    def get_storage(self):
        return self.storage_class()

    def add(self, unit: TranslateToolkitUnit, word: str) -> None:
        unit.target = word

    def create_unit(self, source: str) -> TranslateToolkitUnit:
        return self.storage.UnitClass(source)

    def add_units(self, units: list[Unit]) -> None:
        for unit in units:
            self.add_unit(unit)

    def build_unit(self, unit: Unit) -> TranslateToolkitUnit:
        output = self.create_unit(self.handle_plurals(unit.get_source_plurals()))
        # Propagate source language
        if hasattr(output, "setsource"):
            output.setsource(output.source, sourcelang=self.source_language.code)
        self.add(output, self.handle_plurals(unit.get_target_plurals()))
        return output

    def add_note(self, output, note: str, origin: str) -> None:
        output.addnote(note, origin=origin)

    def add_unit(self, unit: Unit) -> None:
        output = self.build_unit(unit)
        # Location needs to be set prior to ID to avoid overwrite
        # on some formats (for example xliff)
        for location in self.string_filter(unit.location).split(","):
            location = location.strip()
            if location:
                output.addlocation(location)

        # Store context as context and ID
        context = self.string_filter(unit.context)
        if context:
            output.setcontext(context)
            if self.set_id:
                output.setid(context)
        elif self.set_id:
            # Use checksum based ID on formats requiring it
            output.setid(unit.checksum)

        # Store note
        note = self.string_filter(unit.note)
        if note:
            self.add_note(output, note, origin="developer")
        # In Weblate explanation
        note = self.string_filter(unit.source_unit.explanation)
        if note:
            self.add_note(output, note, origin="developer")
        # Comments
        for comment in unit.unresolved_comments:
            self.add_note(
                output, self.string_filter(comment.comment), origin="translator"
            )
        # Suggestions
        for suggestion in unit.suggestions:
            self.add_note(
                output,
                self.string_filter(
                    "Suggested in Weblate: {}".format(
                        ", ".join(split_plural(suggestion.target))
                    )
                ),
                origin="translator",
            )

        # Store flags
        if unit.all_flags:
            self.store_flags(output, unit.all_flags)

        # Store fuzzy flag
        self.store_unit_state(output, unit)

        self.storage.addunit(output)

    def store_unit_state(self, output, unit) -> None:
        if unit.fuzzy:
            output.markfuzzy(True)
        if hasattr(output, "markapproved"):
            output.markapproved(unit.approved)

    def get_filename(self, filetemplate: str = "{path}.{extension}"):
        return filetemplate.format(
            project=self.project.slug,
            language=self.language.code,
            extension=self.extension,
            path="-".join(
                self.translation.get_url_path()
                if self.translation
                else (self.project.slug, self.language.code)
            ),
        )

    def get_response(self, filetemplate: str = "{path}.{extension}"):
        filename = self.get_filename(filetemplate)

        response = HttpResponse(content_type=f"{self.content_type}; charset=utf-8")
        response["Content-Disposition"] = f"attachment; filename={filename}"

        # Save to response
        response.write(self.serialize())

        return response

    def serialize(self) -> bytes:
        """Return storage content."""
        from weblate.formats.ttkit import TTKitFormat

        return TTKitFormat.serialize(self.storage)

    def store_flags(self, output, flags) -> None:
        return
