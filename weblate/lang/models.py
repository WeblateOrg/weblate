# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


import gettext
import re
from collections import defaultdict
from itertools import chain

from appconf import AppConf
from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.db.utils import OperationalError
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy

from weblate.lang import data
from weblate.langdata.aliases import ALIASES
from weblate.langdata.countries import DEFAULT_LANGS
from weblate.langdata.languages import LANGUAGES
from weblate.langdata.plurals import EXTRAPLURALS
from weblate.logger import LOGGER
from weblate.trans.util import sort_objects
from weblate.utils.stats import LanguageStats
from weblate.utils.templatetags.icons import icon
from weblate.utils.validators import validate_pluraleq

PLURAL_RE = re.compile(
    r"\s*nplurals\s*=\s*([0-9]+)\s*;\s*plural\s*=\s*([()n0-9!=|&<>+*/%\s?:-]+)"
)
PLURAL_TITLE = """
{name} <span title="{examples}">{icon}</span>
"""
COPY_RE = re.compile(r"\([0-9]+\)")


def get_plural_type(base_code, pluralequation):
    """Get correct plural type for language."""
    # Remove not needed parenthesis
    if pluralequation[-1] == ";":
        pluralequation = pluralequation[:-1]

    # No plural
    if pluralequation == "0":
        return data.PLURAL_NONE

    # Remove whitespace
    equation = pluralequation.replace(" ", "")

    # Standard plural equations
    for mapping in data.PLURAL_MAPPINGS:
        if equation in mapping[0]:
            return mapping[1]

    # Arabic special case
    if base_code in ("ar",):
        return data.PLURAL_ARABIC

    # Log error in case of uknown mapping
    LOGGER.error("Can not guess type of plural for %s: %s", base_code, pluralequation)

    return data.PLURAL_UNKNOWN


def get_english_lang():
    """Return object ID for English language."""
    try:
        return Language.objects.get_default().id
    except (Language.DoesNotExist, OperationalError):
        return 65535


class LanguageQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def get_default(self):
        """Return default source language object."""
        return self.get(code="en")

    def try_get(self, *args, **kwargs):
        """Try to get language by code."""
        try:
            return self.get(*args, **kwargs)
        except (Language.DoesNotExist, Language.MultipleObjectsReturned):
            return None

    def parse_lang_country(self, code):
        """Parse language and country from locale code."""
        # Strip namespace
        if "~" in code:
            code = code.split(":")[0]

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

        # Handle duplicate language files for example "cs (2)"
        code = COPY_RE.sub("", code)

        # Remove some unwanted characters
        code = code.replace(" ", "").replace("(", "").replace(")", "")

        # Strip leading and trailing .
        code = code.strip(".")

        return code

    def aliases_get(self, code):
        code = code.lower()
        codes = (
            code,
            code.replace("+", "_"),
            code.replace("-", "_"),
            code.replace("-r", "_"),
            code.replace("_r", "_"),
        )
        for newcode in codes:
            if newcode in ALIASES:
                newcode = ALIASES[newcode]
                ret = self.try_get(code=newcode)
                if ret is not None:
                    return ret
        return None

    def fuzzy_get(self, code, strict=False):
        """Get matching language for code.

        The code does not have to be exactly same (cs_CZ is trteated same as
        cs-CZ) or returns None.

        It also handles Android special naming of regional locales like pt-rBR.
        """
        code = self.sanitize_code(code)

        lookups = [
            # First try getting language as is
            Q(code__iexact=code),
            # Replace dash with underscore (for things as zh_Hant)
            Q(code__iexact=code.replace("-", "_")),
            # Try using name
            Q(name__iexact=code),
        ]

        for lookup in lookups:
            # First try getting language as is
            ret = self.try_get(lookup)
            if ret is not None:
                return ret

        # Handle aliases
        ret = self.aliases_get(code)
        if ret is not None:
            return ret

        # Parse the string
        lang, country, subtags = self.parse_lang_country(code)

        # Try "corrected" code
        if country is not None:
            if "@" in country:
                region, variant = country.split("@", 1)
                country = "{0}@{1}".format(region.upper(), variant.lower())
            elif "_" in country:
                # Xliff way of defining variants
                region, variant = country.split("_", 1)
                country = "{0}@{1}".format(region.upper(), variant.lower())
            else:
                country = country.upper()
            newcode = "{0}_{1}".format(lang.lower(), country)
        else:
            newcode = lang.lower()

        if subtags:
            newcode += subtags

        ret = self.try_get(code__iexact=newcode)
        if ret is not None:
            return ret

        # Try canonical variant
        if settings.SIMPLIFY_LANGUAGES and newcode.lower() in DEFAULT_LANGS:
            ret = self.try_get(code=lang.lower())
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
        """Automatically create new language.

        It is based on code and best guess of parameters.
        """
        # Create standard language
        name = "{0} (generated)".format(code)
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
                    equation=baseplural.equation,
                )
        elif create:
            lang.plural_set.create(
                source=Plural.SOURCE_DEFAULT, number=2, equation="n != 1"
            )

        return lang

    def setup(self, update, logger=lambda x: x):
        """Create basic set of languages.

        It is based on languages defined in the languages-data repo.
        """
        # Create Weblate languages
        for code, name, nplurals, pluraleq in LANGUAGES:
            lang, created = self.get_or_create(code=code, defaults={"name": name})
            if created:
                logger("Created language {}".format(code))

            # Get plural type
            plural_type = get_plural_type(lang.base_code, pluraleq)

            # Should we update existing?
            if update and lang.name != name:
                lang.name = name
                logger("Updated language {}".format(code))
                lang.save()

            plural_data = {
                "type": plural_type,
                "number": nplurals,
                "equation": pluraleq,
            }
            try:
                plural, created = lang.plural_set.get_or_create(
                    source=Plural.SOURCE_DEFAULT, language=lang, defaults=plural_data
                )
                if created:
                    logger(
                        "Created default plural {} for language {}".format(
                            pluraleq, code
                        )
                    )
                else:
                    modified = False
                    for item in plural_data:
                        if getattr(plural, item) != plural_data[item]:
                            modified = True
                            setattr(plural, item, plural_data[item])
                    if modified:
                        logger(
                            "Updated default plural {} for language {}".format(
                                pluraleq, code
                            )
                        )
                        plural.save()
            except Plural.MultipleObjectsReturned:
                continue

        # Create addditiona plurals
        for code, _unused, nplurals, pluraleq in EXTRAPLURALS:
            lang = self.get(code=code)

            # Get plural type
            plural_type = get_plural_type(lang.base_code, pluraleq)

            plural_data = {"type": plural_type}
            plural, created = lang.plural_set.get_or_create(
                source=Plural.SOURCE_GETTEXT,
                language=lang,
                number=nplurals,
                equation=pluraleq,
                defaults=plural_data,
            )
            if created:
                logger("Created plural {} for language {}".format(pluraleq, code))
            else:
                modified = False
                for item in plural_data:
                    if getattr(plural, item) != plural_data[item]:
                        modified = True
                        setattr(plural, item, plural_data[item])
                if modified:
                    logger("Updated plural {} for language {}".format(pluraleq, code))
                    plural.save()

    def have_translation(self):
        """Return list of languages which have at least one translation."""
        return self.exclude(translation=None).order()

    def order(self):
        return self.order_by("name")

    def order_translated(self):
        return sort_objects(self)


def setup_lang(sender, **kwargs):
    """Hook for creating basic set of languages on database migration."""
    with transaction.atomic():
        Language.objects.setup(False)


class Language(models.Model):
    code = models.SlugField(unique=True, verbose_name=gettext_lazy("Language code"))
    name = models.CharField(max_length=100, verbose_name=gettext_lazy("Language name"))
    direction = models.CharField(
        verbose_name=gettext_lazy("Text direction"),
        max_length=3,
        default="ltr",
        choices=(
            ("ltr", gettext_lazy("Left to right")),
            ("rtl", gettext_lazy("Right to left")),
        ),
    )

    objects = LanguageQuerySet.as_manager()

    class Meta:
        verbose_name = gettext_lazy("Language")
        verbose_name_plural = gettext_lazy("Languages")

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super().__init__(*args, **kwargs)
        self._plural_examples = {}
        self.stats = LanguageStats(self)

    def __str__(self):
        if self.show_language_code:
            return "{0} ({1})".format(_(self.name), self.code)
        return _(self.name)

    @property
    def show_language_code(self):
        return self.code not in data.NO_CODE_LANGUAGES

    def get_absolute_url(self):
        return reverse("show_language", kwargs={"lang": self.code})

    def get_html(self):
        """Return html attributes for markup in this language.

        Includes language and direction HTML.
        """
        return mark_safe('lang="{0}" dir="{1}"'.format(self.code, self.direction))

    def save(self, *args, **kwargs):
        """Set default direction for language."""
        if self.base_code in data.RTL_LANGS:
            self.direction = "rtl"
        else:
            self.direction = "ltr"
        return super().save(*args, **kwargs)

    @cached_property
    def base_code(self):
        return self.code.replace("_", "-").split("-")[0]

    def uses_ngram(self):
        return self.base_code in ("ja", "zh", "ko")

    @cached_property
    def plural(self):
        return self.plural_set.filter(source=Plural.SOURCE_DEFAULT)[0]


class PluralQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("source")


class Plural(models.Model):
    PLURAL_CHOICES = (
        (data.PLURAL_NONE, pgettext_lazy("Plural type", "None")),
        (
            data.PLURAL_ONE_OTHER,
            pgettext_lazy("Plural type", "One/other (classic plural)"),
        ),
        (
            data.PLURAL_ONE_FEW_OTHER,
            pgettext_lazy("Plural type", "One/few/other (Slavic languages)"),
        ),
        (data.PLURAL_ARABIC, pgettext_lazy("Plural type", "Arabic languages")),
        (data.PLURAL_ZERO_ONE_OTHER, pgettext_lazy("Plural type", "Zero/one/other")),
        (data.PLURAL_ONE_TWO_OTHER, pgettext_lazy("Plural type", "One/two/other")),
        (data.PLURAL_ONE_OTHER_TWO, pgettext_lazy("Plural type", "One/other/two")),
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
        (data.PLURAL_ONE_OTHER_ZERO, pgettext_lazy("Plural type", "One/other/zero")),
        (
            data.PLURAL_ONE_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "One/few/many/other"),
        ),
        (data.PLURAL_TWO_OTHER, pgettext_lazy("Plural type", "Two/other")),
        (
            data.PLURAL_ONE_TWO_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "One/two/few/many/other"),
        ),
        (data.PLURAL_UNKNOWN, pgettext_lazy("Plural type", "Unknown")),
        (
            data.PLURAL_ZERO_ONE_TWO_FEW_MANY_OTHER,
            pgettext_lazy("Plural type", "Zero/one/two/few/many/other"),
        ),
    )
    SOURCE_DEFAULT = 0
    SOURCE_GETTEXT = 1
    SOURCE_MANUAL = 2
    source = models.SmallIntegerField(
        default=SOURCE_DEFAULT,
        verbose_name=gettext_lazy("Plural definition source"),
        choices=(
            (SOURCE_DEFAULT, gettext_lazy("Default plural")),
            (SOURCE_GETTEXT, gettext_lazy("Plural gettext formula")),
            (SOURCE_MANUAL, gettext_lazy("Manually entered formula")),
        ),
    )
    number = models.SmallIntegerField(
        default=2, verbose_name=gettext_lazy("Number of plurals")
    )
    equation = models.CharField(
        max_length=600,
        default="n != 1",
        validators=[validate_pluraleq],
        blank=False,
        verbose_name=gettext_lazy("Plural equation"),
    )
    type = models.IntegerField(
        choices=PLURAL_CHOICES,
        default=data.PLURAL_ONE_OTHER,
        verbose_name=gettext_lazy("Plural type"),
        editable=False,
    )
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)

    objects = PluralQuerySet.as_manager()

    class Meta:
        verbose_name = gettext_lazy("Plural form")
        verbose_name_plural = gettext_lazy("Plural forms")

    def __str__(self):
        return self.get_type_display()

    @cached_property
    def plural_form(self):
        return "nplurals={0:d}; plural={1};".format(self.number, self.equation)

    @cached_property
    def plural_function(self):
        return gettext.c2py(self.equation if self.equation else "0")

    @cached_property
    def examples(self):
        result = defaultdict(list)
        func = self.plural_function
        for i in chain(range(0, 10000), range(10000, 2000001, 1000)):
            ret = func(i)
            if len(result[ret]) >= 10:
                continue
            result[ret].append(str(i))
        return result

    @staticmethod
    def parse_formula(plurals):
        matches = PLURAL_RE.match(plurals)
        if matches is None:
            raise ValueError("Failed to parse formula")

        number = int(matches.group(1))
        formula = matches.group(2)
        if not formula:
            formula = "0"
        # Try to parse the formula
        gettext.c2py(formula)

        return number, formula

    def same_plural(self, number, equation):
        """Compare whether given plurals formula matches."""
        if number != self.number or not equation:
            return False

        # Convert formulas to functions
        ours = self.plural_function
        theirs = gettext.c2py(equation)

        # Compare equation results
        # It would be better to compare formulas,
        # but this was easier to implement and the performance
        # is still okay.
        for i in range(-10, 200):
            if ours(i) != theirs(i):
                return False

        return True

    def get_plural_label(self, idx):
        """Return label for plural form."""
        return PLURAL_TITLE.format(
            name=self.get_plural_name(idx),
            icon=icon("info.svg"),
            # Translators: Label for plurals with example counts
            examples=_("For example: {0}").format(
                ", ".join(self.examples.get(idx, []))
            ),
        )

    def get_plural_name(self, idx):
        """Return name for plural form."""
        try:
            return force_str(data.PLURAL_NAMES[self.type][idx])
        except (IndexError, KeyError):
            if idx == 0:
                return _("Singular")
            if idx == 1:
                return _("Plural")
            return _("Plural form %d") % idx

    def list_plurals(self):
        for i in range(self.number):
            yield {
                "index": i,
                "name": self.get_plural_name(i),
                "examples": ", ".join(self.examples.get(i, [])),
            }

    def save(self, *args, **kwargs):
        self.type = get_plural_type(self.language.base_code, self.equation)
        # Try to calculate based on equation
        if self.type == data.PLURAL_UNKNOWN:
            for equations, plural in data.PLURAL_MAPPINGS:
                for equation in equations:
                    if self.same_plural(self.number, equation):
                        self.type = plural
                        break
                if self.type != data.PLURAL_UNKNOWN:
                    break
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return "{}#information".format(
            reverse("show_language", kwargs={"lang": self.language.code})
        )


class WeblateLanguagesConf(AppConf):
    """Languages settings."""

    # Use simple language codes for default language/country combinations
    SIMPLIFY_LANGUAGES = True

    class Meta:
        prefix = ""
