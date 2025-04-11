# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for language manipulations."""

import warnings
from gettext import c2py
from io import StringIO
from itertools import chain
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.translation import activate
from weblate_language_data.aliases import ALIASES
from weblate_language_data.languages import LANGUAGES
from weblate_language_data.plurals import CLDRPLURALS, EXTRAPLURALS, QTPLURALS
from weblate_language_data.population import POPULATION

from weblate.lang import data
from weblate.lang.models import Language, Plural, PluralMapper, get_plural_type
from weblate.trans.models import Unit
from weblate.trans.tests.test_models import BaseTestCase
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase
from weblate.trans.util import join_plural
from weblate.utils.db import using_postgresql
from weblate.utils.state import STATE_TRANSLATED

TEST_LANGUAGES = (
    ("cs_CZ", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("cze_CZ", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("ces_CZ", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    (
        "cs_latn",
        "cs_Latn",
        "ltr",
        "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
        "Czech (cs_Latn)",
        True,
    ),
    ("cs (2)", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("cscz", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    ("czech", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False),
    (
        "cs_CZ@hantec",
        "cs_CZ@hantec",
        "ltr",
        "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2",
        "Czech (cs_CZ@hantec)",
        True,
    ),
    ("de-DE", "de", "ltr", "n != 1", "German", False),
    ("de_AT", "de_AT", "ltr", "n != 1", "German (Austria)", False),
    ("de_CZ", "de_CZ", "ltr", "n != 1", "German (de_CZ)", True),
    ("portuguese_portugal", "pt_PT", "ltr", "n > 1", "Portuguese (Portugal)", False),
    ("pt-rBR", "pt_BR", "ltr", "n > 1", "Portuguese (Brazil)", False),
    ("ptbr", "pt_BR", "ltr", "n > 1", "Portuguese (Brazil)", False),
    (
        "sr+latn",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (Latin script)",
        False,
    ),
    (
        "sr_RS@latin",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (Latin script)",
        False,
    ),
    (
        "sr-RS@latin",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (Latin script)",
        False,
    ),
    (
        "sr_RS_latin",
        "sr_Latn",
        "ltr",
        "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
        "(n%100<10 || n%100>=20) ? 1 : 2",
        "Serbian (Latin script)",
        False,
    ),
    (
        "en_CA_MyVariant",
        "en_CA@myvariant",
        "ltr",
        "n != 1",
        "English (Canada) (en_CA@myvariant)",
        True,
    ),
    ("en_CZ", "en_CZ", "ltr", "n != 1", "English (en_CZ)", True),
    ("zh_CN", "zh_Hans", "ltr", "0", "Chinese (Simplified Han script)", False),
    ("zh-CN", "zh_Hans", "ltr", "0", "Chinese (Simplified Han script)", False),
    ("zh_HANT", "zh_Hant", "ltr", "0", "Chinese (Traditional Han script)", False),
    ("zh-HANT", "zh_Hant", "ltr", "0", "Chinese (Traditional Han script)", False),
    (
        "zh-CN@test",
        "zh_CN@test",
        "ltr",
        "0",
        "Chinese (Simplified Han script) (zh_CN@test)",
        True,
    ),
    ("zh-rCN", "zh_Hans", "ltr", "0", "Chinese (Simplified Han script)", False),
    ("zh_rCN", "zh_Hans", "ltr", "0", "Chinese (Simplified Han script)", False),
    (
        "zh_HK",
        "zh_Hant_HK",
        "ltr",
        "0",
        "Chinese (Traditional Han script, Hong Kong)",
        False,
    ),
    (
        "zh_Hant-rHK",
        "zh_Hant_HK",
        "ltr",
        "0",
        "Chinese (Traditional Han script, Hong Kong)",
        False,
    ),
    (
        "ar",
        "ar",
        "rtl",
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
        ": n%100>=11 ? 4 : 5",
        "Arabic",
        False,
    ),
    (
        "ar_AA",
        "ar",
        "rtl",
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
        ": n%100>=11 ? 4 : 5",
        "Arabic",
        False,
    ),
    (
        "ar_XX",
        "ar_XX",
        "rtl",
        "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 "
        ": n%100>=11 ? 4 : 5",
        "Arabic (ar_XX)",
        True,
    ),
    ("xx", "xx", "ltr", "n != 1", "xx (generated) (xx)", True),
    ("nb_NO", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    ("nb-NO", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    ("nb", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    ("nono", "nb_NO", "ltr", "n != 1", "Norwegian Bokmål", False),
    (
        "b+zh+Hant+HK",
        "zh_Hant_HK",
        "ltr",
        "0",
        "Chinese (Traditional Han script, Hong Kong)",
        False,
    ),
    (
        "plPL",
        "pl",
        "ltr",
        "n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2",
        "Polish",
        False,
    ),
)


# Constants for BasicLanguagesTest

# bit masks
BASE_FORM = 1
BASE_ALIAS = 1 << 1
BASE_VARIANT = 1 << 2

# combinations
BASE_LANGUAGE_ONLY = BASE_FORM
DEFAULT_VARIANT_ONLY = BASE_ALIAS
TWO_VARIANTS_ONLY = BASE_ALIAS | BASE_VARIANT
BASE_PLUS_VARIANT = BASE_FORM | BASE_VARIANT

TEST_LANGUAGE_GROUPS = (
    # We've got 'en' language and its variants like 'en_US' and 'en_GB' will not be present in the default list of basic languages
    ("en", None, "en_US", "en_GB", BASE_LANGUAGE_ONLY),
    # There is no standalone 'zh' language but rather 'zh_Hans' and 'zh_Hant' as UNDERSCORE_EXCEPTIONS
    ("zh", "zh_Hans", "zh_Hant", TWO_VARIANTS_ONLY),
    # The base language 'be' stands alongside 'be_Latn' as basic languages
    ("be", None, "be_Latn", BASE_PLUS_VARIANT),
    # Both the base language and a variant in UNDERSCORE_EXCEPTIONS as basic languages
    ("pt", None, "pt_BR", BASE_PLUS_VARIANT),
    # 'nb' being alias for the 'nb_NO' language instead
    ("nb", "nb_NO", DEFAULT_VARIANT_ONLY),
    # We no longer have standalone 'yue' and 'nan' languages, so keep their aliases 'yue_Hant' and 'nan_Hant' in basic languages instead
    ("yue", "yue_Hant", "yue_Hans", DEFAULT_VARIANT_ONLY),
    ("nan", "nan_Hant", "nan_Latn", DEFAULT_VARIANT_ONLY),
)


class BasicLanguagesTest(TestCase):
    """Test for the default list of basic languages."""

    @staticmethod
    def check_presence(languages, reference=False):
        result = 0
        base_alias = None
        for i, lang in enumerate(languages):
            if lang is None:
                continue
            if reference:
                if i == 0:
                    check = lang in data.NO_CODE_LANGUAGES
                else:
                    if i == 1:
                        base_language = languages[0]
                        if base_language in ALIASES:
                            base_alias = ALIASES[base_language]
                    check = (
                        lang == base_alias and not result & BASE_FORM
                    ) or lang in data.UNDERSCORE_EXCEPTIONS
            else:
                check = lang in data.BASIC_LANGUAGES
            result += check << i
        if reference:
            if base_alias is None or base_alias == languages[1]:
                return (result,)
            return result, base_alias, base_alias in data.BASIC_LANGUAGES
        return result

    @staticmethod
    def list_languages(bitset, languages):
        langs = []
        for i, lang in enumerate(languages):
            if bitset & 1 << i:
                langs.append(lang)
        return langs or None

    @staticmethod
    def get_friendly_result(result, expected, languages) -> str:
        return f"Expecting {__class__.list_languages(expected, languages)} but got {__class__.list_languages(result, languages)} in basic languages."

    def run_test(self, language_group, adaptive=None) -> None:
        *language_forms, expected = language_group
        result = self.check_presence(language_forms)
        if adaptive is not None and result != expected:
            base_language = language_forms[0]
            adapted, *base_alias = self.check_presence(language_forms, True)
            if adapted != expected:
                warnings.warn(
                    f"Unexpected results for '{base_language}' language group. Adapting test case to current language-data.",
                    stacklevel=1,
                )
                adaptive.append(base_language)
            if adapted == 0:
                self.skipTest(
                    f"Never mind. '{base_language}' is not present in the list of languages and no alias is found."
                )
            expected = adapted
            if not expected & BASE_FORM and base_alias:
                self.assertTrue(
                    base_alias[1],
                    f"There is no standalone '{base_language}' language and its alias '{base_alias[0]}' is not present in basic languages.",
                )
        self.assertEqual(
            result, expected, self.get_friendly_result(result, expected, language_forms)
        )

    def test_basic_languages(self) -> None:
        heads_up = []
        for i, lang in enumerate(TEST_LANGUAGE_GROUPS):
            with self.subTest(f"Testing the '{lang[0]}' language group", i=i):
                self.run_test(lang, heads_up)
        if heads_up:
            warnings.warn(
                f"Perhaps the test case needs to catch up with language-data for {heads_up}?",
                stacklevel=1,
            )


class LanguageTestSequenceMeta(type):
    def __new__(mcs, name, bases, dict):  # noqa: A002
        def gen_test(original, expected, direction, plural, name, create):
            def test(self) -> None:
                self.run_create(original, expected, direction, plural, name, create)

            return test

        for params in TEST_LANGUAGES:
            test_name = "test_create_{}".format(
                params[0].replace("@", "___").replace("+", "_").replace("-", "__")
            )
            if test_name in dict:
                msg = f"Duplicate test: {params[0]}, mapped to {test_name}"
                raise ValueError(msg)
            dict[test_name] = gen_test(*params)

        return type.__new__(mcs, name, bases, dict)


class LanguagesTest(BaseTestCase, metaclass=LanguageTestSequenceMeta):
    def setUp(self) -> None:
        # Ensure we're using English
        activate("en")

    def run_create(self, original, expected, direction, plural, name, create) -> None:
        """Test that auto create correctly handles languages."""
        # Lookup language
        lang = Language.objects.auto_get_or_create(original, create=False)
        self.assertEqual(
            create,
            not bool(lang.pk),
            f"Could not assert creation for {original}: {create}",
        )
        # Create language
        lang = Language.objects.auto_get_or_create(original)
        # Check language code
        self.assertEqual(
            lang.code, expected, f"Invalid code for {original}: {lang.code}"
        )
        # Check direction
        self.assertEqual(lang.direction, direction, f"Invalid direction for {original}")
        # Check plurals
        plural_obj = lang.plural_set.get(source=Plural.SOURCE_DEFAULT)
        self.assertEqual(
            plural_obj.formula,
            plural,
            f"Invalid plural for {original} "
            f"(expected {plural}, got {plural_obj.formula})",
        )
        # Check whether html contains both language code and direction
        self.assertIn(direction, lang.get_html())
        self.assertIn(expected, lang.get_html())
        # Check name
        self.assertEqual(str(lang), name)

    def test_private_use(self, code="de-x-a123", expected="de-x-a123") -> None:
        lang = Language.objects.auto_get_or_create(code, create=False)
        self.assertEqual(lang.code, expected)
        Language.objects.create(name="Test", code=code)
        lang = Language.objects.auto_get_or_create(code, create=False)
        self.assertEqual(lang.code, code)

    def test_private_country(self) -> None:
        self.test_private_use("en-US-x-twain", "en_US-x-twain")

    def test_private_fuzzy_get(self) -> None:
        Language.objects.auto_get_or_create("cs_FOO")
        self.run_create(
            "czech", "cs", "ltr", "(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2", "Czech", False
        )

    def test_dan(self) -> None:
        """Test that aliases have higher priority than language names."""
        language = Language.objects.auto_get_or_create("dan")
        self.assertEqual(language.code, "da")

    def test_chinese_fuzzy_get(self) -> None:
        """Test handling of manually created zh_CN language."""
        language = Language.objects.create(code="zh_CN", name="Chinese")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create("zh-rCN", "zh_CN", "ltr", "0", "Chinese (zh_CN)", False)

    def test_case_sensitive_fuzzy_get(self) -> None:
        """Test handling of manually created zh-TW, zh-TW and zh_TW languages."""
        if not using_postgresql():
            self.skipTest("Not supported on MySQL")

        language = Language.objects.create(code="zh_TW", name="Chinese (Taiwan)")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create("zh_TW", "zh_TW", "ltr", "0", "Chinese (Taiwan) (zh_TW)", False)
        language = Language.objects.create(code="zh-TW", name="Chinese Taiwan")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create("zh-TW", "zh-TW", "ltr", "0", "Chinese Taiwan (zh-TW)", False)
        language = Language.objects.create(code="zh-tw", name="Traditional Chinese")
        language.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.run_create(
            "zh-tw", "zh-tw", "ltr", "0", "Traditional Chinese (zh-tw)", False
        )


class CommandTest(BaseTestCase):
    """Test for management commands."""

    def test_setuplang(self) -> None:
        call_command("setuplang")
        self.assertTrue(Language.objects.exists())
        with self.assertNumQueries(3):
            call_command("setuplang")

    def test_setuplang_noupdate(self) -> None:
        call_command("setuplang", update=False)
        self.assertTrue(Language.objects.exists())

    def check_list(self, **kwargs) -> None:
        output = StringIO()
        call_command("list_languages", "cs", stdout=output, **kwargs)
        self.assertIn("Czech", output.getvalue())

    def test_list_languages(self) -> None:
        self.check_list()

    def test_list_languages_lower(self) -> None:
        self.check_list(lower=True)

    def test_move_language(self) -> None:
        Language.objects.auto_create("cs_CZ")
        call_command("move_language", "cs_CZ", "cs")


class VerifyPluralsTest(TestCase):
    """In database plural form verification."""

    @staticmethod
    def all_data():
        return chain(LANGUAGES, EXTRAPLURALS, CLDRPLURALS)

    def test_valid(self) -> None:
        """Validate that we can name all plural formulas."""
        for code, _name, _nplurals, plural_formula in self.all_data():
            self.assertNotEqual(
                get_plural_type(code.replace("_", "-").split("-")[0], plural_formula),
                data.PLURAL_UNKNOWN,
                f"Can not guess plural type for {code}: {plural_formula}",
            )

    def test_with_zero(self) -> None:
        for _code, _name, _nplurals, plural_formula in CLDRPLURALS:
            self.assertIn(plural_formula, data.FORMULA_WITH_ZERO)
            with_zero = data.FORMULA_WITH_ZERO[plural_formula]
            c2py(with_zero)

    def test_formula(self) -> None:
        """Validate that all formulas can be parsed by gettext."""
        # Verify we get an error on invalid syntax
        with self.assertRaises((SyntaxError, ValueError)):
            c2py("n==0 ? 1 2")
        for code, _name, nplurals, plural_formula in self.all_data():
            # Validate plurals can be parsed
            plural = c2py(plural_formula)
            # Get maximal plural
            calculated = max(plural(x) for x in range(200)) + 1
            # Check it matches ours
            self.assertEqual(
                calculated,
                nplurals,
                f"Invalid nplurals for {code}: calculated={calculated} (number={nplurals}, formula={plural_formula})",
            )


class LanguagesViewTest(FixtureTestCase):
    def test_languages(self) -> None:
        response = self.client.get(reverse("languages"))
        self.assertContains(response, "Czech")

    def test_language(self) -> None:
        response = self.client.get(reverse("show_language", kwargs={"lang": "cs"}))
        self.assertContains(response, "Czech")
        self.assertContains(response, "test/test")

    def test_language_br(self) -> None:
        response = self.client.get(reverse("show_language", kwargs={"lang": "br"}))
        self.assertContains(response, "Breton")
        # Example is listed
        self.assertContains(response, "1000000")

    def test_project_language(self) -> None:
        response = self.client.get(
            reverse(
                "project-language-redirect", kwargs={"lang": "cs", "project": "test"}
            ),
            follow=True,
        )
        self.assertRedirects(
            response,
            reverse("show", kwargs={"path": ["test", "-", "cs"]}),
            status_code=301,
        )
        self.assertContains(response, "Czech")
        self.assertContains(response, "/projects/test/test/cs/")

    def test_language_redirect(self) -> None:
        response = self.client.get(reverse("show_language", kwargs={"lang": "cs_CZ"}))
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "cs"}))

    def test_language_nonexisting(self) -> None:
        response = self.client.get(
            reverse("show_language", kwargs={"lang": "nonexisting"})
        )
        self.assertEqual(response.status_code, 404)

    def test_add(self) -> None:
        response = self.client.get(reverse("create-language"))
        self.assertEqual(response.status_code, 302)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("create-language"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("create-language"), {"code": "x"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            reverse("create-language"),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "number": "2",
                "formula": "n != 1",
                "population": 10,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))

    def test_delete(self) -> None:
        response = self.client.post(reverse("show_language", kwargs={"lang": "br"}))
        self.assertEqual(response.status_code, 200)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(reverse("show_language", kwargs={"lang": "cs"}))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("show_language", kwargs={"lang": "br"}))
        self.assertRedirects(response, reverse("languages"))

    def test_edit(self) -> None:
        language = Language.objects.get(code="cs")
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-language", kwargs={"pk": language.pk}),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "population": 10,
                "workflow-suggestion_autoaccept": 0,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))

    def test_edit_workflow(self) -> None:
        language = Language.objects.get(code="cs")
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-language", kwargs={"pk": language.pk}),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "population": 10,
                "workflow-enable": 1,
                "workflow-translation_review": 1,
                "workflow-suggestion_autoaccept": 0,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))
        self.assertTrue(language.workflowsetting_set.exists())
        response = self.client.post(
            reverse("edit-language", kwargs={"pk": language.pk}),
            {
                "code": "xx",
                "name": "XX",
                "direction": "ltr",
                "population": 10,
                "workflow-translation_review": 1,
                "workflow-suggestion_autoaccept": 0,
            },
        )
        self.assertRedirects(response, reverse("show_language", kwargs={"lang": "xx"}))
        self.assertFalse(language.workflowsetting_set.exists())

    def test_edit_plural(self) -> None:
        language = Language.objects.get(code="cs")
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("edit-plural", kwargs={"pk": language.plural.pk}),
            {"number": "2", "formula": "n != 1"},
        )
        self.assertRedirects(
            response, reverse("show_language", kwargs={"lang": "cs"}) + "#information"
        )


class PluralsCompareTest(TestCase):
    def test_match(self) -> None:
        plural = Plural.objects.get(language__code="cs", source=Plural.SOURCE_DEFAULT)
        self.assertTrue(plural.same_plural(plural.number, plural.formula))

    def test_formula(self) -> None:
        plural = Plural.objects.get(language__code="pt", source=Plural.SOURCE_DEFAULT)
        self.assertFalse(plural.same_plural(2, "(n != 1)"))

    def test_different_formula(self) -> None:
        plural = Plural.objects.get(language__code="pt", source=Plural.SOURCE_DEFAULT)
        self.assertTrue(plural.same_plural(2, "(n > 1)"))

    def test_different_count(self) -> None:
        plural = Plural.objects.get(language__code="lt", source=Plural.SOURCE_DEFAULT)
        self.assertFalse(
            plural.same_plural(
                4,
                "(n%10==1 ? 0 : n%10==1 && n%100!=11 ?"
                " 1 : n %10>=2 && (n%100<10 || n%100>=20) ? 2 : 3)",
            )
        )

    def test_invalid(self) -> None:
        plural = Plural.objects.get(language__code="lt", source=Plural.SOURCE_DEFAULT)
        self.assertFalse(plural.same_plural(1, "bogus"))


class PluralTest(BaseTestCase):
    def test_examples(self) -> None:
        plural = Plural(number=2, formula="n!=1")
        self.assertEqual(
            plural.examples,
            {0: ["1"], 1: ["0", "2", "3", "4", "5", "6", "7", "8", "9", "10", "…"]},
        )

    def test_plurals(self) -> None:
        """Test whether plural form is correctly calculated."""
        plural = Plural.objects.get(language__code="cs", source=Plural.SOURCE_DEFAULT)
        self.assertEqual(
            plural.plural_form,
            "nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;",
        )

    def test_plural_names(self) -> None:
        plural = Plural.objects.get(language__code="cs", source=Plural.SOURCE_DEFAULT)
        self.assertEqual(plural.get_plural_name(0), "One")
        self.assertEqual(plural.get_plural_name(1), "Few")
        self.assertEqual(plural.get_plural_name(2), "Many")

    def test_plural_names_invalid(self) -> None:
        plural = Plural.objects.get(language__code="cs", source=Plural.SOURCE_DEFAULT)
        plural.type = -1
        self.assertEqual(plural.get_plural_name(0), "Singular")
        self.assertEqual(plural.get_plural_name(1), "Plural")
        self.assertEqual(plural.get_plural_name(2), "Plural form 2")

    def test_plural_labels(self) -> None:
        plural = Plural.objects.get(language__code="cs", source=Plural.SOURCE_DEFAULT)
        label = plural.get_plural_label(0)
        self.assertIn("One", label)
        self.assertIn("1", label)
        label = plural.get_plural_label(1)
        self.assertIn("Few", label)
        self.assertIn("2, 3, 4", label)
        label = plural.get_plural_label(2)
        self.assertIn("Many", label)
        self.assertIn("5, 6, 7", label)

    def test_plural_type(self) -> None:
        language = Language.objects.get(code="cs")
        plural = Plural.objects.create(
            language=language,
            number=3,
            formula=(
                "(n%10==1 && n%100!=11 ? 0 : "
                "n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)"
            ),
            source=Plural.SOURCE_GETTEXT,
        )
        self.assertEqual(plural.type, data.PLURAL_ONE_FEW_MANY)

    def test_definitions(self) -> None:
        """Verify consistency of plural definitions."""
        plurals = [x[1] for x in data.PLURAL_MAPPINGS]
        choices = [x[0] for x in Plural.PLURAL_CHOICES]
        for plural in plurals:
            self.assertIn(plural, choices)
            self.assertIn(plural, data.PLURAL_NAMES)


class PluralMapperTestCase(FixtureTestCase):
    def test_english_czech(self) -> None:
        english = Language.objects.get(code="en")
        czech = Language.objects.get(code="cs")
        mapper = PluralMapper(english.plural, czech.plural)
        self.assertEqual(mapper.target_map, ((0, None), (None, None), (-1, None)))
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        self.assertEqual(
            mapper.map(unit),
            ["Orangutan has %d banana.\n", "", "Orangutan has %d bananas.\n"],
        )

    def test_czech_german(self) -> None:
        german = Language.objects.get(code="de")
        czech = Language.objects.get(code="cs")
        mapper = PluralMapper(czech.plural, german.plural)
        self.assertEqual(mapper.target_map, ((0, None), (-1, None)))
        unit = Unit.objects.get(
            translation__language=czech, id_hash=2097404709965985808
        )
        unit.translate(None, ["one\n", "few\n", "other\n"], STATE_TRANSLATED)
        unit = Unit.objects.get(
            translation__language=german, id_hash=2097404709965985808
        )
        others = mapper.get_other_units([unit], czech)
        self.assertIn(2097404709965985808, others)
        other = others[2097404709965985808]
        self.assertEqual(
            mapper.map(unit, other),
            ["one\n", "other\n"],
        )

    def test_russian_english(self) -> None:
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper.target_map, ((0, 1), (-1, None)))
        # Use English here to test incomplete plural set in the source string
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        self.assertEqual(
            mapper.map(unit),
            ["Orangutan has %d banana.\n", "Orangutan has %d bananas.\n"],
        )

    def test_russian_english_interpolate(self) -> None:
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper.target_map, ((0, 1), (-1, None)))
        # Use English here to test incomplete plural set in the source string
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        unit.extra_flags = "python-brace-format"
        unit.source = unit.source.replace("%d", "{count}")
        self.assertEqual(
            mapper.map(unit),
            ["Orangutan has 1 banana.\n", "Orangutan has {count} bananas.\n"],
        )

    def test_russian_english_interpolate_double(self) -> None:
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper.target_map, ((0, 1), (-1, None)))
        # Use English here to test incomplete plural set in the source string
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        unit.extra_flags = "python-brace-format"
        unit.source = unit.source.replace("%d", "{count} {count}")
        self.assertEqual(
            mapper.map(unit),
            [
                "Orangutan has {count} {count} banana.\n",
                "Orangutan has {count} {count} bananas.\n",
            ],
        )

    def test_russian_english_interpolate_missing(self) -> None:
        russian = Language.objects.get(code="ru")
        english = Language.objects.get(code="en")
        mapper = PluralMapper(russian.plural, english.plural)
        self.assertEqual(mapper.target_map, ((0, 1), (-1, None)))
        unit = Unit.objects.get(
            translation__language=english, id_hash=2097404709965985808
        )
        unit.extra_flags = "i18next-interpolation"
        unit.source = join_plural(["{{periodNumber}}-я четверть"] * 3)
        self.assertEqual(
            mapper.map(unit),
            ["{{periodNumber}}-я четверть", "{{periodNumber}}-я четверть"],
        )

    def test_arabic_aliases(self) -> None:
        arabic = Language.objects.get(code="ar")
        self.assertEqual(arabic.get_aliases_names(), ["ar_aa", "ar_ar", "ara", "arb"])
        with override_settings(SIMPLIFY_LANGUAGES=True):
            self.assertEqual(
                arabic.get_aliases_names(), ["ar_aa", "ar_ar", "ara", "arb"]
            )
        with override_settings(SIMPLIFY_LANGUAGES=False):
            self.assertEqual(arabic.get_aliases_names(), ["ar_ar", "ara", "arb"])


class LanguageAliasesChangeTest(ViewTestCase):
    """Simulate language aliases change in weblate_language_data and test results."""

    old_code = "it"
    new_code = "it_XX"

    def setUp(self) -> None:
        """Set up test environment."""
        super().setUp()

        def update_codes_in_dict(data: dict) -> dict:
            """Replace old_code key with new_code in a language dict."""
            copy = data.copy()
            value = copy.pop(self.old_code)
            copy[self.new_code] = value
            return copy

        def update_code_in_tuple(data: tuple) -> tuple:
            """Replace old_code with new_code in a language tuple."""
            new_data = []
            for item in data:
                if item[0] == self.old_code:
                    item = (self.new_code, *item[1:])
                new_data.append(item)
            return tuple(new_data)

        updated_aliases = ALIASES | {self.old_code: self.new_code}

        patch_values = [
            (
                "weblate_language_data.languages.LANGUAGES",
                update_code_in_tuple(LANGUAGES),
            ),
            (
                "weblate_language_data.population.POPULATION",
                update_codes_in_dict(POPULATION),
            ),
            ("weblate.lang.models.EXTRAPLURALS", update_code_in_tuple(EXTRAPLURALS)),
            ("weblate.lang.models.QTPLURALS", update_code_in_tuple(QTPLURALS)),
            ("weblate.lang.models.CLDRPLURALS", update_code_in_tuple(CLDRPLURALS)),
            ("weblate_language_data.aliases.ALIASES", updated_aliases),
            ("weblate.lang.data.ALIASES", updated_aliases),
            ("weblate.lang.models.ALIASES", updated_aliases),
        ]

        for target, new_value in patch_values:
            patcher = patch(target, new_value)
            patcher.start()

    def tearDown(self) -> None:
        """Tear down after tests."""
        super().tearDown()
        patch.stopall()

    def do_alias_language_update_and_check(
        self, new_language_created: bool = True, old_language_deleted: bool = True
    ) -> None:
        """Test alias language update."""

        def component_language_codes():
            """Get current language codes for component translations."""
            return [
                translation.language.code
                for translation in self.component.translation_set.all()
            ]

        self.assertIn(self.old_code, component_language_codes())
        logs: list[str] = []
        Language.objects.setup(update=True, logger=logs.append)
        if new_language_created:
            self.assertIn(f"Created language {self.new_code}", logs)
        else:
            self.assertNotIn(f"Created language {self.new_code}", logs)

        self.assertIn(self.new_code, component_language_codes())
        if old_language_deleted:
            # alias language should be deleted if blank
            self.assertFalse(Language.objects.filter(code=self.old_code).exists())
        else:
            self.assertIn(self.old_code, component_language_codes())
            self.assertTrue(Language.objects.filter(code=self.old_code).exists())

    def test_update_language_alias(self) -> None:
        """Test simple alias change."""
        self.do_alias_language_update_and_check()

    def test_update_language_alias_no_deletion(self) -> None:
        """Test alias change with no deletion of old language."""
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        it_xx = Language.objects.create(code="it_XX", name="New Italian")
        it_xx.plural_set.create(
            number=0,
            formula="0",
            source=Plural.SOURCE_DEFAULT,
        )
        self.component.add_new_language(it_xx, None)
        self.do_alias_language_update_and_check(False, False)
