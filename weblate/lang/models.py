# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from gettext import c2py
from itertools import chain
from typing import Callable
from weakref import WeakValueDictionary

from appconf import AppConf
from django.conf import settings
from django.db import models, transaction
from django.db.models import Exists, OuterRef, Q
from django.db.utils import OperationalError
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy, pgettext_lazy
from django.utils.translation.trans_real import parse_accept_lang_header
from weblate_language_data.aliases import ALIASES
from weblate_language_data.countries import DEFAULT_LANGS
from weblate_language_data.plurals import CLDRPLURALS, EXTRAPLURALS
from weblate_language_data.rtl import RTL_LANGS

from weblate.checks.format import BaseFormatCheck
from weblate.checks.models import CHECKS
from weblate.lang import data
from weblate.logger import LOGGER
from weblate.trans.defines import LANGUAGE_CODE_LENGTH, LANGUAGE_NAME_LENGTH
from weblate.trans.mixins import CacheKeyMixin
from weblate.trans.util import sort_objects, sort_unicode
from weblate.utils.validators import validate_plural_formula

PLURAL_RE = re.compile(
    r"\s*nplurals\s*=\s*([0-9]+)\s*;\s*plural\s*=\s*([()n0-9!=|&<>+*/%\s?:-]+)"
)
PLURAL_TITLE = """
{name} <span class="text-muted" title="{title}">({examples})</span>
"""
COPY_RE = re.compile(r"\([0-9]+\)")
KNOWN_SUFFIXES = {"hant", "hans", "latn", "cyrl", "shaw"}


def get_plural_type(base_code, plural_formula):
    """Get correct plural type for language."""
    # Remove not needed parenthesis
    if plural_formula[-1] == ";":
        plural_formula = plural_formula[:-1]

    # No plural
    if plural_formula == "0":
        return data.PLURAL_NONE

    # Remove whitespace
    formula = plural_formula.replace(" ", "")

    # Standard plural formulas
    for mapping in data.PLURAL_MAPPINGS:
        if formula in mapping[0]:
            return mapping[1]

    # Arabic special case
    if base_code in ("ar",):
        return data.PLURAL_ARABIC

    # Log error in case of unknown mapping
    LOGGER.error("Can not guess type of plural for %s: %s", base_code, plural_formula)

    # Try to calculate based on formula
    for formulas, plural in data.PLURAL_MAPPINGS:
        for data_formula in formulas:
            if is_same_plural(-1, plural_formula, -1, data_formula):
                return plural

    return data.PLURAL_UNKNOWN


def is_same_plural(
    our_number: int,
    our_formula: str,
    number: int,
    formula: str,
    our_function: Callable | None = None,
    plural_function: Callable | None = None,
):
    if our_function is None:
        try:
            our_function = c2py(our_formula)
        except ValueError:
            return False

    if plural_function is None:
        try:
            plural_function = c2py(formula)
        except ValueError:
            return False

    if number not in (-1, our_number):
        return False
    if formula == our_formula:
        return True
    # Compare formula results
    # It would be better to compare formulas,
    # but this was easier to implement and the performance
    # is still okay.
    return all(
        our_function(i) == plural_function(i)
        for i in chain(range(-10, 200), [1000, 10000, 100000, 1000000, 10000000])
    )


def get_default_lang():
    """Return object ID for English language."""
    try:
        return Language.objects.default_language.id
    except (Language.DoesNotExist, OperationalError):
        return -1


class LanguageQuerySet(models.QuerySet):
    def try_get(self, *args, **kwargs):
        """Try to get language by code."""
        result = self.filter(*args, **kwargs)[:2]
        if len(result) != 1:
            return None
        return result[0]

    @staticmethod
    def parse_lang_country(code):
        """Parse language and country from locale code."""
        # Parse private use subtag
        subtag_pos = code.find("-x-")
        if subtag_pos != -1:
            subtag = code[subtag_pos:]
            code = code[:subtag_pos]
        else:
            subtag = ""
        # Parse the string
        if "-" in code:
            lang, country = code.split("-", 1)
            # Android regional locales
            if len(country) > 2 and country[0] == "r":
                country = country[1:]
        elif "_" in code:
            lang, country = code.split("_", 1)
        elif "+" in code:
            lang, country = code.split("+", 1)
        else:
            lang = code
            country = None

        return lang, country, subtag

    @staticmethod
    def sanitize_code(code):
        """Language code sanitization."""
        # Strip b+ prefix from Android
        if code.startswith("b+"):
            code = code[2:]

        # Replace -r from Android by _
        if len(code) == 6 and "-r" in code:
            code = code.replace("-r", "_")

        # Handle duplicate language files for example "cs (2)"
        code = COPY_RE.sub("", code)

        # Remove some unwanted characters
        code = code.replace(" ", "").replace("(", "").replace(")", "")

        # Strip leading and trailing .
        return code.strip(".")

    def aliases_get(self, code, expanded_code=None):
        code = code.lower()
        # Normalize script suffix
        code = code.replace("_latin", "@latin").replace("_cyrillic", "@cyrillic")
        codes = [code]
        codes.extend(
            code.replace(replacement, "_")
            for replacement in ("+", "-", "-r", "_r")
            if replacement in code
        )
        if expanded_code and expanded_code != code:
            codes.append(expanded_code)

        # Lookup in aliases
        for newcode in codes:
            if newcode in ALIASES:
                testcode = ALIASES[newcode]
                ret = self.try_get(code=testcode)
                if ret is not None:
                    return ret

        # Alias language code only
        for newcode in codes:
            language, _sep, country = newcode.partition("_")
            if (
                country
                and len(language) > 2
                and language in ALIASES
                and "_" not in ALIASES[language]
            ):
                testcode = f"{ALIASES[language]}_{country}"
                ret = self.fuzzy_get(code=testcode, strict=True)
                if ret is not None:
                    return ret

        return None

    def fuzzy_get(self, code, strict=False):
        """
        Get matching language for code.

        The code does not have to be exactly same (cs_CZ is trteated same as
        cs-CZ) or returns None.

        It also handles Android special naming of regional locales like pt-rBR.
        """
        code = self.sanitize_code(code)
        expanded_code = None

        lookups = [
            # First try getting language as is (case-sensitive)
            Q(code=code),
            # Then try getting language as is (case-insensitive)
            Q(code__iexact=code),
            # Replace dash with underscore (for things as zh_Hant)
            Q(code__iexact=code.replace("-", "_")),
            # Replace plus with underscore (for things as zh+Hant+HK on Android)
            Q(code__iexact=code.replace("+", "_")),
            # Try using name
            Q(name__iexact=code) & Q(code__in=data.NO_CODE_LANGUAGES),
        ]

        # Country codes used without underscore (ptbr insteat of pt_BR)
        if len(code) == 4:
            expanded_code = f"{code[:2]}_{code[2:]}".lower()
            lookups.append(Q(code__iexact=expanded_code))

        for lookup in lookups:
            # First try getting language as is
            ret = self.try_get(lookup)
            if ret is not None:
                return ret

        # Handle aliases
        ret = self.aliases_get(code, expanded_code)
        if ret is not None:
            return ret

        # Parse the string
        lang, country, subtags = self.parse_lang_country(code)

        # Try "corrected" code
        if country is not None:
            if "@" in country:
                region, variant = country.split("@", 1)
                country = f"{region.upper()}@{variant.lower()}"
            elif "_" in country:
                # Xliff way of defining variants
                region, variant = country.split("_", 1)
                country = f"{region.upper()}@{variant.lower()}"
            elif country in KNOWN_SUFFIXES:
                country = country.title()
            else:
                country = country.upper()
            newcode = f"{lang.lower()}_{country}"
        else:
            newcode = lang.lower()

        if subtags:
            newcode += subtags

        ret = self.try_get(code__iexact=newcode)
        if ret is not None:
            return ret

        # Try canonical variant
        if settings.SIMPLIFY_LANGUAGES:
            if newcode.lower() in DEFAULT_LANGS:
                ret = self.try_get(code=lang.lower())
            elif expanded_code in DEFAULT_LANGS:
                ret = self.try_get(code=expanded_code[:2])
            if ret is not None:
                return ret

        return None if strict else newcode

    def auto_get_or_create(self, code, create=True):
        """Try to get language using fuzzy_get and create it if that fails."""
        ret = self.fuzzy_get(code)
        if isinstance(ret, Language):
            return ret

        # Create new one
        return self.auto_create(ret, create)

    def auto_create(self, code, create=True):
        """
        Automatically create new language.

        It is based on code and best guess of parameters.
        """
        # Create standard language
        name = f"{code} (generated)"
        if create:
            lang = self.get_or_create(code=code, defaults={"name": name})[0]
        else:
            lang = Language(code=code, name=name)

        baselang = None

        # Check for different variant
        if baselang is None and "@" in code:
            parts = code.split("@")
            baselang = self.fuzzy_get(code=parts[0], strict=True)

        # Check for different country
        if baselang is None and "_" in code or "-" in code:
            parts = code.replace("-", "_").split("_")
            baselang = self.fuzzy_get(code=parts[0], strict=True)

        if baselang is not None:
            lang.name = baselang.name
            lang.direction = baselang.direction
            if create:
                lang.save()
                baseplural = baselang.plural
                lang.plural_set.create(
                    source=Plural.SOURCE_DEFAULT,
                    number=baseplural.number,
                    formula=baseplural.formula,
                )
        elif create:
            lang.plural_set.create(
                source=Plural.SOURCE_DEFAULT, number=2, formula="n != 1"
            )

        return lang

    def have_translation(self):
        """Return list of languages which have at least one translation."""
        from weblate.trans.models import Translation

        return self.filter(Exists(Translation.objects.filter(language=OuterRef("pk"))))

    def order(self):
        return self.order_by("name")

    def order_translated(self):
        return sort_objects(self)

    def get_by_code(self, code, cache, langmap=None):
        """Cached and aliases aware getter."""
        if code in cache:
            return cache[code]
        if langmap and code in langmap:
            language = self.fuzzy_get(code=langmap[code], strict=True)
        else:
            language = self.fuzzy_get(code=code, strict=True)
        if language is None:
            raise Language.DoesNotExist(code)
        cache[code] = language
        return language

    def as_choices(self, use_code: bool = True):
        return (
            item[:2]
            for item in sort_unicode(
                (
                    (code if use_code else pk, f"{gettext(name)} ({code})", name)
                    for pk, name, code in self.values_list("pk", "name", "code")
                ),
                lambda tup: tup[2],
            )
        )

    def get(self, *args, **kwargs):
        """Customized get caching getting of English language."""
        if not args and not kwargs.pop("skip_cache", False):
            default = Language.objects.default_language
            if kwargs in (
                {"code": settings.DEFAULT_LANGUAGE},
                {"pk": default.pk},
                {"id": default.id},
            ):
                return default
        return super().get(*args, **kwargs)

    def get_request_language(self, request):
        """
        Guess user language from a HTTP request.

        Accept-Language HTTP header, for most browser it consists of browser
        language with higher rank and OS language with lower rank so it still
        might be usable guess.
        """
        accept = request.headers.get("accept-language", "")
        for accept_lang, _unused in parse_accept_lang_header(accept):
            if accept_lang == "en":
                continue
            try:
                return self.get(code=accept_lang)
            except Language.DoesNotExist:
                continue
        return None

    def search(self, query: str):
        return self.filter(Q(name__icontains=query) | Q(code__icontains=query))

    def prefetch(self):
        return self.prefetch_related("plural_set")


class LanguageManager(models.Manager.from_queryset(LanguageQuerySet)):
    use_in_migrations = True

    def flush_object_cache(self):
        if "default_language" in self.__dict__:
            del self.__dict__["default_language"]

    @cached_property
    def default_language(self):
        """Return English language object."""
        return self.get(code=settings.DEFAULT_LANGUAGE, skip_cache=True)

    def setup(self, update, logger=lambda x: x):
        """
        Create basic set of languages.

        It is based on languages defined in the languages-data repo.
        """
        from weblate_language_data.languages import LANGUAGES
        from weblate_language_data.population import POPULATION

        # Invalidate cache, we might change languages
        self.flush_object_cache()
        languages = {language.code: language for language in self.prefetch()}
        plurals = {}
        # Create Weblate languages
        for code, name, nplurals, plural_formula in LANGUAGES:
            population = POPULATION[code]

            if code in languages:
                lang = languages[code]
            else:
                languages[code] = lang = self.create(
                    code=code, name=name, population=population
                )
                logger(f"Created language {code}")

            direction = lang.guess_direction()
            # Should we update existing?
            if update and (
                lang.name != name
                or lang.direction != direction
                or lang.population != population
            ):
                lang.name = name
                lang.direction = direction
                lang.population = population
                logger(f"Updated language {code}")
                lang.save()

            plural_data = {
                "number": nplurals,
                "formula": plural_formula,
            }

            # Fetch existing plurals
            plurals[code] = defaultdict(list)
            for plural in lang.plural_set.iterator():
                plurals[code][plural.source].append(plural)

            if Plural.SOURCE_DEFAULT in plurals[code]:
                plural = plurals[code][Plural.SOURCE_DEFAULT][0]
                modified = False
                for item in plural_data:
                    if getattr(plural, item) != plural_data[item]:
                        modified = True
                        setattr(plural, item, plural_data[item])
                if modified:
                    logger(
                        f"Updated default plural {plural_formula} for language {code}"
                    )
                    plural.save()
            else:
                plural = lang.plural_set.create(
                    source=Plural.SOURCE_DEFAULT, language=lang, **plural_data
                )
                plurals[code][Plural.SOURCE_DEFAULT].append(plural)
                logger(f"Created default plural {plural_formula} for language {code}")

        # Create addditiona plurals
        extra_plurals = (
            (Plural.SOURCE_GETTEXT, EXTRAPLURALS),
            (Plural.SOURCE_CLDR, CLDRPLURALS),
        )
        for source, definitions in extra_plurals:
            for code, _unused, nplurals, plural_formula in definitions:
                lang = languages[code]

                for plural in plurals[code][source]:
                    try:
                        if plural.same_plural(nplurals, plural_formula):
                            break
                    except ValueError:
                        # Fall back to string compare if parsing failed
                        if (
                            plural.number == nplurals
                            and plural.formula == plural_formula
                        ):
                            break
                else:
                    plural = lang.plural_set.create(
                        source=source,
                        number=nplurals,
                        formula=plural_formula,
                        type=get_plural_type(lang.base_code, plural_formula),
                    )
                    logger(f"Created plural {plural_formula} for language {code}")

        self._fixup_plural_types(logger)

    def _fixup_plural_types(self, logger):
        """Fixes plural types as they were changed in Weblate codebase."""
        if not Plural.objects.filter(type=data.PLURAL_ONE_FEW_MANY).exists():
            for plural in Plural.objects.filter(
                type=data.PLURAL_ONE_FEW_OTHER
            ).select_related("language"):
                language = plural.language
                newtype = get_plural_type(language.base_code, plural.formula)
                if newtype == data.PLURAL_UNKNOWN:
                    raise ValueError(f"Invalid plural type of {plural.formula}")
                if newtype != plural.type:
                    plural.type = newtype
                    plural.save(update_fields=["type"])
                    logger(
                        f"Updated type of {plural.formula} for language {language.code}"
                    )


def setup_lang(sender, **kwargs):
    """Hook for creating basic set of languages on database migration."""
    if settings.UPDATE_LANGUAGES:
        with transaction.atomic():
            Language.objects.setup(True)


class Language(models.Model, CacheKeyMixin):
    code = models.SlugField(
        max_length=LANGUAGE_CODE_LENGTH,
        unique=True,
        verbose_name=gettext_lazy("Language code"),
    )
    name = models.CharField(
        max_length=LANGUAGE_NAME_LENGTH, verbose_name=gettext_lazy("Language name")
    )
    direction = models.CharField(
        verbose_name=gettext_lazy("Text direction"),
        max_length=3,
        default="",
        choices=(
            ("", ""),
            ("ltr", gettext_lazy("Left to right")),
            ("rtl", gettext_lazy("Right to left")),
        ),
    )
    population = models.BigIntegerField(
        gettext_lazy("Number of speakers"),
        help_text=gettext_lazy("Number of people speaking this language."),
        default=0,
    )

    objects = LanguageManager()

    class Meta:
        verbose_name = "Language"
        verbose_name_plural = "Languages"
        # Use own manager to utilize caching of English
        base_manager_name = "objects"

    def __str__(self):
        if self.show_language_code:
            return f"{gettext(self.name)} ({self.code})"
        return gettext(self.name)

    def save(self, *args, **kwargs):
        """Set default direction for language."""
        if not self.direction:
            self.direction = self.guess_direction()
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("show_language", kwargs={"lang": self.code})

    def get_url_path(self):
        return ("-", "-", self.code)

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        from weblate.utils.stats import LanguageStats

        super().__init__(*args, **kwargs)
        self._plural_examples = {}
        self.stats = LanguageStats(self)

    def get_name(self):
        """Not localized version of __str__."""
        if self.show_language_code:
            return f"{self.name} ({self.code})"
        return self.name

    def guess_direction(self):
        if self.base_code in RTL_LANGS or self.code in RTL_LANGS:
            return "rtl"
        return "ltr"

    @property
    def show_language_code(self):
        return self.code not in data.NO_CODE_LANGUAGES

    def get_html(self):
        """
        Return html attributes for markup in this language.

        Includes language and direction HTML.
        """
        return format_html('lang="{}" dir="{}"', self.code, self.direction)

    @cached_property
    def base_code(self):
        return self.code.replace("_", "-").split("-")[0]

    def uses_ngram(self):
        return self.base_code in ("ja", "zh", "ko")

    @cached_property
    def plural(self):
        if self.plural_set.all()._result_cache is not None:
            for plural in self.plural_set.all():
                if plural.source == Plural.SOURCE_DEFAULT:
                    return plural
        return self.plural_set.filter(source=Plural.SOURCE_DEFAULT)[0]

    def get_aliases_names(self):
        return [alias for alias, codename in ALIASES.items() if codename == self.code]


class PluralQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("source")


class Plural(models.Model):
    PLURAL_CHOICES = (
        (
            data.PLURAL_NONE,
            pgettext_lazy("Plural type", "None"),
        ),
        (
            data.PLURAL_ONE_OTHER,
            pgettext_lazy("Plural type", "One/other"),
        ),
        (
            data.PLURAL_ONE_FEW_OTHER,
            pgettext_lazy("Plural type", "One/few/other"),
        ),
        (
            data.PLURAL_ARABIC,
            pgettext_lazy("Plural type", "Arabic languages"),
        ),
        (
            data.PLURAL_ZERO_ONE_OTHER,
            pgettext_lazy("Plural type", "Zero/one/other"),
        ),
        (
            data.PLURAL_ONE_TWO_OTHER,
            pgettext_lazy("Plural type", "One/two/other"),
        ),
        (
            data.PLURAL_ONE_OTHER_TWO,
            pgettext_lazy("Plural type", "One/other/two"),
        ),
        (
            data.PLURAL_ONE_TWO_FEW_OTHER,
            pgettext_lazy("Plural type", "One/two/few/other"),
        ),
        (
            data.PLURAL_OTHER_ONE_TWO_FEW,
            pgettext_lazy("Plural type", "Other/one/two/few"),
        ),
        (
            data.PLURAL_ONE_TWO_THREE_OTHER,
            pgettext_lazy("Plural type", "One/two/three/other"),
        ),
        (
            data.PLURAL_ONE_OTHER_ZERO,
            pgettext_lazy("Plural type", "One/other/zero"),
        ),
        (
            data.PLURAL_ONE_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "One/few/many/other"),
        ),
        (
            data.PLURAL_TWO_OTHER,
            pgettext_lazy("Plural type", "Two/other"),
        ),
        (
            data.PLURAL_ONE_TWO_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "One/two/few/many/other"),
        ),
        (
            data.PLURAL_ZERO_ONE_TWO_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "Zero/one/two/few/many/other"),
        ),
        (
            data.PLURAL_ZERO_OTHER,
            pgettext_lazy("Plural type", "Zero/other"),
        ),
        (
            data.PLURAL_ZERO_ONE_FEW_OTHER,
            pgettext_lazy("Plural type", "Zero/one/few/other"),
        ),
        (
            data.PLURAL_ZERO_ONE_TWO_FEW_OTHER,
            pgettext_lazy("Plural type", "Zero/one/two/few/other"),
        ),
        (
            data.PLURAL_ZERO_ONE_TWO_OTHER,
            pgettext_lazy("Plural type", "Zero/one/two/other"),
        ),
        (
            data.PLURAL_ZERO_ONE_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "Zero/one/few/many/other"),
        ),
        (
            data.PLURAL_ONE_MANY_OTHER,
            pgettext_lazy("Plural type", "One/many/other"),
        ),
        (
            data.PLURAL_ZERO_ONE_MANY_OTHER,
            pgettext_lazy("Plural type", "Zero/one/many/other"),
        ),
        (
            data.PLURAL_ONE_FEW_MANY,
            pgettext_lazy("Plural type", "One/few/many"),
        ),
        (
            data.PLURAL_UNKNOWN,
            pgettext_lazy("Plural type", "Unknown"),
        ),
    )
    SOURCE_DEFAULT = 0
    SOURCE_GETTEXT = 1
    SOURCE_MANUAL = 2
    SOURCE_CLDR_ZERO = 3
    SOURCE_CLDR = 4
    SOURCE_ANDROID = 5
    source = models.SmallIntegerField(
        default=SOURCE_DEFAULT,
        verbose_name=gettext_lazy("Plural definition source"),
        choices=(
            (SOURCE_DEFAULT, gettext_lazy("Default plural")),
            (SOURCE_GETTEXT, gettext_lazy("gettext plural formula")),
            (SOURCE_CLDR_ZERO, gettext_lazy("CLDR plural with zero")),
            (SOURCE_CLDR, gettext_lazy("CLDR v38+ plural")),
            (SOURCE_ANDROID, gettext_lazy("Android plural")),
            (SOURCE_MANUAL, gettext_lazy("Manually entered formula")),
        ),
    )
    number = models.SmallIntegerField(
        default=2, verbose_name=gettext_lazy("Number of plurals")
    )
    formula = models.TextField(
        default="n != 1",
        validators=[validate_plural_formula],
        blank=False,
        verbose_name=gettext_lazy("Plural formula"),
    )
    type = models.IntegerField(
        choices=PLURAL_CHOICES,
        default=data.PLURAL_UNKNOWN,
        verbose_name=gettext_lazy("Plural type"),
        editable=False,
    )
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)

    objects = PluralQuerySet.as_manager()

    class Meta:
        verbose_name = "Plural form"
        verbose_name_plural = "Plural forms"

    def __str__(self):
        return self.get_type_display()

    def save(self, *args, **kwargs):
        self.type = get_plural_type(self.language.base_code, self.formula)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return "{}#information".format(
            reverse("show_language", kwargs={"lang": self.language.code})
        )

    @cached_property
    def plural_form(self):
        return f"nplurals={self.number:d}; plural={self.formula};"

    @cached_property
    def plural_function(self):
        try:
            return c2py(self.formula if self.formula else "0")
        except ValueError as error:
            raise ValueError(f"Could not compile formula {self.formula!r}: {error}")

    @cached_property
    def examples(self):
        result = defaultdict(list)
        func = self.plural_function
        for i in chain(range(10000), range(10000, 2000001, 1000)):
            ret = func(i)  # pylint: disable=too-many-function-args
            if len(result[ret]) >= 10:
                continue
            result[ret].append(str(i))
        for example in result.values():
            if len(example) >= 10:
                example.append("…")
        return result

    @staticmethod
    def parse_plural_forms(plurals):
        matches = PLURAL_RE.match(plurals)
        if matches is None:
            raise ValueError("Could not parse plural forms")

        number = int(matches.group(1))
        formula = matches.group(2)
        if not formula:
            formula = "0"
        # Try to parse the formula
        c2py(formula)

        return number, formula

    def same_as(self, other):
        """Check whether the given plurals are equivalent."""
        return is_same_plural(
            self.number,
            self.formula,
            other.number,
            other.formula,
            our_function=self.plural_function,
            plural_function=other.plural_function,
        )

    def same_plural(self, number: int, formula: str):
        """Compare whether given plurals formula matches."""
        return is_same_plural(
            self.number,
            self.formula,
            number,
            formula,
            our_function=self.plural_function,
        )

    def get_plural_label(self, idx):
        """Return label for plural form."""
        return format_html(
            PLURAL_TITLE,
            name=self.get_plural_name(idx),
            examples=", ".join(self.examples.get(idx, [])),
            title=gettext("Example counts for this plural form."),
        )

    def get_plural_name(self, idx):
        """Return name for plural form."""
        try:
            return str(data.PLURAL_NAMES[self.type][idx])
        except (IndexError, KeyError):
            if idx == 0:
                return gettext("Singular")
            if idx == 1:
                return gettext("Plural")
            return gettext("Plural form %d") % idx

    def list_plurals(self):
        for i in range(self.number):
            yield {
                "index": i,
                "name": self.get_plural_name(i),
                "examples": ", ".join(self.examples.get(i, [])),
            }


class PluralMapper:
    instances = WeakValueDictionary()

    def __new__(cls, source_plural, target_plural):
        key = (source_plural.formula, target_plural.formula)
        obj = cls.instances.get(key)
        if obj is None:
            obj = cls.instances[key] = super().__new__(cls)
        return obj

    def __init__(self, source_plural, target_plural):
        self.source_plural = source_plural
        self.target_plural = target_plural
        self.same_plurals = source_plural.same_as(target_plural)

    @cached_property
    def _target_map(self):
        exact_source_map = {}
        all_source_map = {}
        for i, examples in self.source_plural.examples.items():
            if len(examples) == 1:
                exact_source_map[examples[0]] = i
            else:
                for example in examples:
                    all_source_map[example] = i

        target_plural = self.target_plural
        target_map = []
        last = target_plural.number - 1
        for i in range(target_plural.number):
            examples = target_plural.examples.get(i, ())
            if len(examples) == 1:
                number = examples[0]
                if number in exact_source_map:
                    target_map.append((exact_source_map[number], None))
                elif number in all_source_map:
                    target_map.append((all_source_map[number], number))
                else:
                    target_map.append((-1, number))
            elif i == last:
                target_map.append((-1, None))
            else:
                target_map.append((None, None))
        return tuple(target_map)

    def map(self, unit):
        source_strings = unit.get_source_plurals()
        if self.same_plurals or len(source_strings) == 1:
            strings_to_translate = source_strings
        elif self.target_plural.number == 1:
            strings_to_translate = [source_strings[-1]]
        else:
            strings_to_translate = []
            format_check = next(
                (
                    check
                    for check in CHECKS.values()
                    if (
                        isinstance(check, BaseFormatCheck)
                        and check.enable_string in unit.all_flags
                        and check.plural_parameter_regexp
                    )
                ),
                None,
            )
            for source_index, number_to_interpolate in self._target_map:
                s = "" if source_index is None else source_strings[source_index]
                if s and number_to_interpolate is not None and format_check:
                    s = format_check.interpolate_number(s, number_to_interpolate)
                strings_to_translate.append(s)
        return strings_to_translate

    def zip(self, sources, targets, unit):
        if len(sources) != self.source_plural.number:
            raise ValueError(
                "length of `sources` does't match the number of source plurals"
            )
        if len(targets) != self.target_plural.number:
            raise ValueError(
                "length of `targets` does't match the number of target plurals"
            )
        if self.same_plurals:
            return zip(sources, targets)
        return [
            (sources[-1 if i is None else i], targets[j])
            for (i, _), j in zip(self._target_map, range(len(targets)))
        ]


class WeblateLanguagesConf(AppConf):
    """Languages settings."""

    # Update languages on migration
    UPDATE_LANGUAGES = True

    # Use simple language codes for default language/country combinations
    SIMPLIFY_LANGUAGES = True

    # Default source languaage
    DEFAULT_LANGUAGE = "en"

    # List of basic languages to show for user when adding new translation
    BASIC_LANGUAGES = None

    class Meta:
        prefix = ""
