#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Base classes for file formats."""

import os
import tempfile
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from django.utils.functional import cached_property
from django.utils.translation import gettext as _
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


class UnitNotFound(Exception):
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
    """Wrapper for translate-toolkit unit.

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
        raise NotImplementedError()

    @cached_property
    def target(self):
        """Return target string from a ttkit unit."""
        raise NotImplementedError()

    @cached_property
    def context(self):
        """Return context of message.

        In some cases we have to use ID here to make all backends consistent.
        """
        raise NotImplementedError()

    @cached_property
    def previous_source(self):
        """Return previous message source if there was any."""
        return ""

    @classmethod
    def calculate_id_hash(cls, has_template: bool, source: str, context: str):
        """Return hash of source string, used for quick lookup.

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

    def set_target(self, target: Union[str, List[str]]):
        """Set translation unit target."""
        raise NotImplementedError()

    def set_state(self, state):
        """Set fuzzy /approved flag on translated unit."""
        raise NotImplementedError()

    def has_unit(self) -> bool:
        return self.unit is not None

    def clone_template(self):
        self.mainunit = self.unit = deepcopy(self.template)


class TranslationFormat:
    """Generic object defining file format loader."""

    name: str = ""
    format_id: str = ""
    monolingual: Optional[bool] = None
    check_flags: Tuple[str, ...] = ()
    unit_class: Type[TranslationUnit] = TranslationUnit
    autoload: Tuple[str, ...] = ()
    can_add_unit: bool = True
    language_format: str = "posix"
    simple_filename: bool = True
    new_translation: Optional[Union[str, bytes]] = None
    autoaddon: Dict[str, Dict[str, str]] = {}
    create_empty_bilingual: bool = False
    bilingual_class = None
    create_style = "create"
    has_multiple_strings: bool = False

    @classmethod
    def get_identifier(cls):
        return cls.format_id

    @classmethod
    def parse(
        cls,
        storefile,
        template_store=None,
        language_code: Optional[str] = None,
        source_language: Optional[str] = None,
        is_template: bool = False,
    ):
        """Parse store and returns TranslationFormat instance.

        This wrapper is needed for AutodetectFormat to be able to return instance of
        different class.
        """
        return cls(
            storefile,
            template_store=template_store,
            language_code=language_code,
            source_language=source_language,
            is_template=is_template,
        )

    def __init__(
        self,
        storefile,
        template_store=None,
        language_code: Optional[str] = None,
        source_language: Optional[str] = None,
        is_template: bool = False,
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

        # Load store
        self.store = self.load(storefile, template_store)

        self.add_breadcrumb(
            "Loaded translation file {}".format(
                getattr(storefile, "filename", storefile)
            ),
            template_store=str(template_store),
            is_template=is_template,
        )

    def check_valid(self):
        """Check store validity."""
        if not self.is_valid():
            raise ValueError(
                _("Failed to load strings from the file, try choosing other format.")
            )

    def get_filenames(self):
        if isinstance(self.storefile, str):
            return [self.storefile]
        return [self.storefile.name]

    def load(self, storefile, template_store):
        raise NotImplementedError()

    @classmethod
    def get_plural(cls, language, store=None):
        """Return matching plural object."""
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
        self, context: str, source: str, id_hash: Optional[int] = None
    ) -> Optional[Any]:
        if id_hash is None:
            id_hash = self._calculate_string_hash(context, source)
        try:
            # The mono units always have only template set
            return self._template_index[id_hash].template
        except KeyError:
            return None

    def _find_unit_monolingual(self, context: str, source: str) -> Tuple[Any, bool]:
        # We search by ID when using template
        id_hash = self._calculate_string_hash(context, source)
        try:
            result = self._unit_index[id_hash]
        except KeyError:
            raise UnitNotFound(context, source)

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

    def _find_unit_bilingual(self, context: str, source: str) -> Tuple[Any, bool]:
        id_hash = self._calculate_string_hash(context, source)
        try:
            return (self._unit_index[id_hash], False)
        except KeyError:
            raise UnitNotFound(context, source)

    def find_unit(self, context: str, source: Optional[str] = None) -> Tuple[Any, bool]:
        """Find unit by context and source.

        Returns tuple (ttkit_unit, created) indicating whether returned unit is new one.
        """
        if self.has_template:
            return self._find_unit_monolingual(context, source)
        return self._find_unit_bilingual(context, source)

    def add_unit(self, ttkit_unit):
        """Add new unit to underlying store."""
        raise NotImplementedError()

    def update_header(self, **kwargs):
        """Update store header if available."""
        return

    def save_atomic(self, filename, callback):
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
        raise NotImplementedError()

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
        # Make sure we do not have a collision in id_hash
        hashes = set()
        for unit in self.content_units:
            if unit.id_hash in hashes:
                raise ValueError(f"Duplicate id_hash for unit {unit.unit}")
            hashes.add(unit.id_hash)
        return True

    @classmethod
    def is_valid_base_for_new(
        cls,
        base: str,
        monolingual: bool,
        errors: Optional[List] = None,
        fast: bool = False,
    ) -> bool:
        """Check whether base is valid."""
        raise NotImplementedError()

    @classmethod
    def get_language_code(cls, code: str, language_format: Optional[str] = None) -> str:
        """Do any possible formatting needed for language code."""
        if not language_format:
            language_format = cls.language_format
        return getattr(cls, f"get_language_{language_format}")(code)

    @staticmethod
    def get_language_posix(code: str) -> str:
        return code

    @staticmethod
    def get_language_bcp(code: str) -> str:
        return code.replace("_", "-")

    @staticmethod
    def get_language_posix_long(code: str) -> str:
        return EXPAND_LANGS.get(code, code)

    @staticmethod
    def get_language_linux(code: str) -> str:
        """Linux doesn't use Hans/Hant, but rather TW/CN variants."""
        return LEGACY_CODES.get(code, code)

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
    def get_language_java(cls, code: str) -> str:
        """Java doesn't use Hans/Hant, but rather TW/CN variants."""
        return cls.get_language_bcp(cls.get_language_linux(code))

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
        callback: Optional[Callable] = None,
    ):
        """Add new language file."""
        # Create directory for a translation
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cls.create_new_file(filename, language, base, callback)

    @classmethod
    def create_new_file(
        cls,
        filename: str,
        language: str,
        base: str,
        callback: Optional[Callable] = None,
    ):
        """Handle creation of new translation file."""
        raise NotImplementedError()

    def iterate_merge(self, fuzzy: str, only_translated: bool = True):
        """Iterate over units for merging.

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
        source: Union[str, List[str]],
        target: Optional[Union[str, List[str]]] = None,
    ):
        raise NotImplementedError()

    def new_unit(
        self,
        key: str,
        source: Union[str, List[str]],
        target: Optional[Union[str, List[str]]] = None,
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
        raise NotImplementedError()

    @classmethod
    def add_breadcrumb(cls, message, **data):
        add_breadcrumb(category="storage", message=message, **data)

    def delete_unit(self, ttkit_unit) -> Optional[str]:
        raise NotImplementedError()

    def cleanup_unused(self) -> List[str]:
        """Removes unused strings, returning list of additional changed files."""
        if not self.template_store:
            return []
        existing = {unit.context for unit in self.template_store.template_units}
        changed = False

        result = []

        for ttkit_unit in self.all_store_units:
            if self.unit_class(self, ttkit_unit, ttkit_unit).context not in existing:
                item = self.delete_unit(ttkit_unit)
                if item is not None:
                    result.append(item)
                else:
                    changed = True

        if changed:
            self.save()
        return result

    def cleanup_blank(self) -> List[str]:
        """
        Removes strings without translations.

        Returning list of additional changed files.
        """
        changed = False

        result = []

        for ttkit_unit in self.all_store_units:
            target = self.unit_class(self, ttkit_unit, ttkit_unit).target
            if not target or (isinstance(target, list) and not any(target)):
                item = self.delete_unit(ttkit_unit)
                if item is not None:
                    result.append(item)
                else:
                    changed = True

        if changed:
            self.save()
        return result

    def remove_unit(self, ttkit_unit) -> List[str]:
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
        return result

    @staticmethod
    def validate_context(context: str):
        return


class EmptyFormat(TranslationFormat):
    """For testing purposes."""

    @classmethod
    def load(cls, storefile, template_store):
        return type("", (object,), {"units": []})()

    def save(self):
        return


class BilingualUpdateMixin:
    @classmethod
    def do_bilingual_update(cls, in_file: str, out_file: str, template: str, **kwargs):
        raise NotImplementedError()

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
