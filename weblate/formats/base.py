#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
"""Base classses for file formats."""


import os
import tempfile
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from django.conf import settings
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from sentry_sdk import add_breadcrumb
from weblate_language_data.countries import DEFAULT_LANGS

from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_TRANSLATED

EXPAND_LANGS = {code[:2]: f"{code[:2]}_{code[3:].upper()}" for code in DEFAULT_LANGS}


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

    @cached_property
    def id_hash(self):
        """Return hash of source string, used for quick lookup.

        We use siphash as it is fast and works well for our purpose.
        """
        if self.template is None:
            return calculate_hash(self.source, self.context)
        return calculate_hash(self.context)

    def is_translated(self):
        """Check whether unit is translated."""
        return bool(self.target)

    def is_approved(self, fallback=False):
        """Check whether unit is appoved."""
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

    def set_target(self, target):
        """Set translation unit target."""
        raise NotImplementedError()

    def set_state(self, state):
        """Set fuzzy /approved flag on translated unit."""
        raise NotImplementedError()


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

        # Load store
        self.store = self.load(storefile, template_store)

        # Remember template
        self.template_store = template_store
        self.is_template = is_template
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

    @classmethod
    def load(cls, storefile, template_store):
        raise NotImplementedError()

    def get_plural(self, language):
        """Return matching plural object."""
        return language.plural

    @cached_property
    def has_template(self):
        """Check whether class is using template."""
        return (
            self.monolingual or self.monolingual is None
        ) and self.template_store is not None

    @cached_property
    def _context_index(self):
        """ID based index for units."""
        return {unit.context: unit for unit in self.mono_units}

    def find_unit_mono(self, context: str) -> Optional[Any]:
        try:
            # The mono units always have only template set
            return self._context_index[context].template
        except KeyError:
            return None

    def _find_unit_template(self, context: str) -> Tuple[Any, bool]:
        # Need to create new unit based on template
        template_ttkit_unit = self.template_store.find_unit_mono(context)
        if template_ttkit_unit is None:
            raise UnitNotFound(context)

        # We search by ID when using template
        ttkit_unit = self.find_unit_mono(context)

        # We always need new unit to translate
        if ttkit_unit is None:
            ttkit_unit = deepcopy(template_ttkit_unit)
            add = True
        else:
            add = False

        return (self.unit_class(self, ttkit_unit, template_ttkit_unit), add)

    @cached_property
    def _source_index(self):
        """Context and source based index for units."""
        return {(unit.context, unit.source): unit for unit in self.all_units}

    def _find_unit_bilingual(self, context: str, source: str) -> Tuple[Any, bool]:
        try:
            return (self._source_index[context, source], False)
        except KeyError:
            raise UnitNotFound(context, source)

    def find_unit(self, context: str, source: Optional[str] = None) -> Tuple[Any, bool]:
        """Find unit by context and source.

        Returns tuple (ttkit_unit, created) indicating whether returned unit is new one.
        """
        if self.has_template:
            return self._find_unit_template(context)
        return self._find_unit_bilingual(context, source)

    def add_unit(self, ttkit_unit):
        """Add new unit to underlaying store."""
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
        """Save underlaying store to disk."""
        raise NotImplementedError()

    @property
    def all_store_units(self):
        """Wrapper for all store units for possible filtering."""
        return self.store.units

    @cached_property
    def mono_units(self):
        return [self.unit_class(self, None, unit) for unit in self.all_store_units]

    @cached_property
    def all_units(self):
        """List of all units."""
        if not self.has_template:
            return [self.unit_class(self, unit) for unit in self.all_store_units]
        return [
            self.unit_class(self, self.find_unit_mono(unit.context), unit.template)
            for unit in self.template_store.mono_units
        ]

    @property
    def content_units(self):
        yield from (unit for unit in self.all_units if unit.has_content())

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
        if code in EXPAND_LANGS:
            return EXPAND_LANGS[code]
        return code

    @classmethod
    def get_language_bcp_long(cls, code: str) -> str:
        return cls.get_language_posix_long(code).replace("_", "-")

    @staticmethod
    def get_language_android(code: str) -> str:
        # Android doesn't use Hans/Hant, but rather TW/CN variants
        if code == "zh_Hans":
            return "zh-rCN"
        if code == "zh_Hant":
            return "zh-rTW"
        sanitized = code.replace("-", "_")
        if "_" in sanitized and len(sanitized.split("_")[1]) > 2:
            return "b+{}".format(sanitized.replace("_", "+"))
        return sanitized.replace("_", "-r")

    @classmethod
    def get_language_java(cls, code: str) -> str:
        # Java doesn't use Hans/Hant, but rather TW/CN variants
        if code == "zh_Hans":
            return "zh-CN"
        if code == "zh_Hant":
            return "zh-TW"
        if code == "zh_Hans_SG":
            return "zh-SG"
        if code == "zh_Hant_HK":
            return "zh-HK"
        return cls.get_language_bcp(code)

    @classmethod
    def get_language_filename(cls, mask: str, code: str) -> str:
        """
        Returns full filename of a language file.

        Calculated for given path, filemask and language code.
        """
        return mask.replace("*", code)

    @classmethod
    def add_language(cls, filename, language, base):
        """Add new language file."""
        # Create directory for a translation
        dirname = os.path.dirname(filename)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        cls.create_new_file(filename, language, base)

    @classmethod
    def create_new_file(cls, filename, language, base):
        """Handle creation of new translation file."""
        raise NotImplementedError()

    def iterate_merge(self, fuzzy):
        """Iterate over units for merging.

        Note: This can change fuzzy state of units!
        """
        for unit in self.content_units:
            # Skip fuzzy (if asked for that)
            if unit.is_fuzzy():
                if not fuzzy:
                    continue
            elif not unit.is_translated():
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
                template_unit = self._find_unit_template(key)
        else:
            template_unit = None
        result = self.unit_class(self, unit, template_unit)
        mono_unit = self.unit_class(self, None, unit)

        # Update cached lookups
        if "all_units" in self.__dict__:
            self.all_units.append(result)
        if "mono_units" in self.__dict__:
            self.mono_units.append(mono_unit)
        if "_source_index" in self.__dict__:
            self._source_index[(result.context, result.source)] = result
        if "_context_index" in self.__dict__:
            self._context_index[mono_unit.context] = mono_unit

        return result

    @classmethod
    def get_class(cls):
        raise NotImplementedError()

    @classmethod
    def add_breadcrumb(cls, message, **data):
        if settings.SENTRY_DSN:
            add_breadcrumb(category="storage", message=message, data=data, level="info")

    def delete_unit(self, ttkit_unit) -> Optional[str]:
        raise NotImplementedError()

    def cleanup_unused(self) -> List[str]:
        """Removes unused strings, returning list of additional changed files."""
        existing = {unit.context for unit in self.template_store.mono_units}
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
