# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for widgets."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from django.test import SimpleTestCase
from django.urls import reverse

from weblate.trans.checklists import TranslationChecklistMixin
from weblate.trans.filter import FILTERS
from weblate.trans.models import Translation
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.widgets import WIDGETS
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from django.http import HttpResponse


class EngageTaskObject(TranslationChecklistMixin):
    def __init__(self, stats, enable_review: bool = True) -> None:
        self.stats = stats
        self.enable_review = enable_review

    def get_translate_url(self) -> str:
        return "/translate/"


class EngageTaskChecklistTest(SimpleTestCase):
    """Testing of engage task checklist."""

    def get_engage_tasks(self, **stats):
        obj = EngageTaskObject(
            SimpleNamespace(
                nottranslated=stats.get("nottranslated", 0),
                translated_checks=stats.get("translated_checks", 0),
                suggestions=stats.get("suggestions", 0),
                fuzzy=stats.get("fuzzy", 0),
                unapproved=stats.get("unapproved", 0),
            ),
            stats.get("enable_review", True),
        )
        return cast("Any", obj).list_engage_tasks

    def test_engage_tasks_skip_zero_categories(self) -> None:
        tasks = self.get_engage_tasks(nottranslated=1, fuzzy=2)

        self.assertEqual(
            [(task.url, task.total) for task in tasks],
            [
                ("/translate/?q=state:empty", 1),
                ("/translate/?q=is:needs-editing", 2),
            ],
        )

    def test_fuzzy_filter_query_matches_fuzzy_states(self) -> None:
        self.assertEqual(FILTERS.get_filter_query("fuzzy"), "is:needs-editing")

    def test_engage_tasks_hide_empty_review(self) -> None:
        tasks = self.get_engage_tasks(enable_review=True)

        self.assertEqual(tasks, [])


class WidgetsTest(FixtureTestCase):
    """Testing of widgets."""

    def get_engage_translate_url(self, language: str) -> str:
        return reverse(
            "translate",
            kwargs={"path": [*self.project.get_url_path(), "-", language]},
        )

    def assert_engage_task_urls(
        self, response: HttpResponse, expected_urls: list[str]
    ) -> None:
        task_urls = [
            task.url for task in response.context["translate_object"].list_engage_tasks
        ]
        self.assertEqual(task_urls, expected_urls)

    def assert_engage_task_url(self, response: HttpResponse, expected_url: str) -> None:
        task_urls = [
            task.url for task in response.context["translate_object"].list_engage_tasks
        ]
        self.assertIn(expected_url, task_urls)

    def test_view_widgets(self) -> None:
        response = self.client.get(
            reverse("widgets", kwargs={"path": self.project.get_url_path()})
        )
        self.assertContains(response, "Test")

    def test_view_widgets_lang(self) -> None:
        response = self.client.get(
            reverse("widgets", kwargs={"path": self.project.get_url_path()}),
            {"lang": "cs"},
        )
        self.assertContains(response, "Test")

    def test_view_engage(self) -> None:
        response = self.client.get(
            reverse("engage", kwargs={"path": self.project.get_url_path()})
        )
        self.assertContains(response, "Test")

    def test_view_engage_guessed_language_tasks(self) -> None:
        self.user.profile.language = "en"
        self.user.profile.save(update_fields=["language"])

        response = self.client.get(
            reverse("engage", kwargs={"path": self.project.get_url_path()}),
            headers={"accept-language": "cs"},
        )

        target_url = self.get_engage_translate_url("cs")
        self.assertEqual(response.context["target_language"].code, "cs")
        self.assert_engage_task_urls(response, [f"{target_url}?q=state:empty"])
        self.assertContains(response, "row engage-task-list justify-content-center")
        self.assertContains(response, f"{target_url}?q=state:empty")
        self.assertContains(response, "engage-language-button")
        self.assertContains(response, "engage-button-language")

    def test_view_engage_lang(self) -> None:
        response = self.client.get(
            reverse(
                "engage", kwargs={"path": [*self.project.get_url_path(), "-", "cs"]}
            )
        )
        self.assertContains(response, "Test")
        self.assert_engage_task_urls(
            response, [f"{self.get_engage_translate_url('cs')}?q=state:empty"]
        )
        self.assertContains(response, "row engage-task-list justify-content-center")
        self.assertContains(response, "?q=state:empty")
        self.assertNotContains(response, "?q=is:needs-editing")
        self.assertNotContains(response, "?q=has:check%20AND%20state:%3E=translated")
        self.assertNotContains(response, '?q=has:check"')
        self.assertNotContains(response, "?q=has:suggestion#suggestions")
        self.assertNotContains(response, "state:%3Ctranslated")

    def test_view_engage_lang_suggestion_tasks(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", suggest="yes")

        response = self.client.get(
            reverse(
                "engage", kwargs={"path": [*self.project.get_url_path(), "-", "cs"]}
            )
        )

        self.assert_engage_task_url(
            response,
            f"{self.get_engage_translate_url('cs')}?q=has:suggestion#suggestions",
        )
        self.assertContains(response, "?q=has:suggestion#suggestions")

    def test_view_engage_lang_review_tasks(self) -> None:
        self.project.translation_review = True
        self.project.save()
        self.change_unit("Nazdar svete!\n")

        response = self.client.get(
            reverse(
                "engage", kwargs={"path": [*self.project.get_url_path(), "-", "cs"]}
            )
        )

        self.assert_engage_task_url(
            response, f"{self.get_engage_translate_url('cs')}?q=state:translated"
        )
        self.assertContains(response, "?q=state:translated")

    def test_view_engage_lang_source_review_tasks(self) -> None:
        self.project.source_review = True
        self.project.save()
        unit = self.get_unit(language="en")
        unit.state = STATE_TRANSLATED
        unit.save()
        unit.invalidate_related_cache()

        response = self.client.get(
            reverse(
                "engage", kwargs={"path": [*self.project.get_url_path(), "-", "cs"]}
            )
        )
        self.assertNotContains(response, "?q=state:translated")

        response = self.client.get(
            reverse(
                "engage", kwargs={"path": [*self.project.get_url_path(), "-", "en"]}
            )
        )
        self.assertContains(response, "?q=state:translated")

    def test_site_og(self) -> None:
        response = self.client.get(reverse("og-image"))
        self.assert_png(response)


class WidgetsMeta(type):
    def __new__(mcs, name: str, bases: tuple[type], attrs: dict[str, Any]):
        def gen_test(widget: str, color: str):
            def test(self: WidgetsRenderTest) -> None:
                self.perform_test(widget, color)

            return test

        for widget, widget_data in WIDGETS.items():
            for color in widget_data.colors:
                test_name = f"test_{widget}_{color}"
                attrs[test_name] = gen_test(widget, color)
        return type.__new__(mcs, name, bases, attrs)


class WidgetsRenderTest(FixtureTestCase, metaclass=WidgetsMeta):
    def assert_widget(self, widget: str, response: HttpResponse) -> None:
        if "svg" in WIDGETS[widget].content_type:
            self.assert_svg(response)
        else:
            self.assert_png(response)

    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.project.get_url_path(),
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsPercentRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        for translated in (0, 3, 4):
            # Fake translated stats
            for translation in Translation.objects.iterator():
                translation.stats.ensure_loaded()
                translation.stats.store("translated", translated)
                translation.stats.save()
            response = self.client.get(
                reverse(
                    "widget-image",
                    kwargs={
                        "path": self.project.get_url_path(),
                        "widget": widget,
                        "color": color,
                        "extension": WIDGETS[widget].extension,
                    },
                )
            )

            self.assert_widget(widget, response)


class WidgetsTranslationRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.get_translation().get_url_path(),
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsComponentRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.component.get_url_path(),
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsProjectLanguageRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": [*self.project.get_url_path(), "-", "cs"],
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsLanguageRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": ["-", "-", "cs"],
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsGlobalRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": ["-", "-", "-"],
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsRedirectRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.project.get_url_path(),
                    "widget": widget,
                    "color": color,
                    "extension": "svg",
                },
            ),
            follow=True,
        )

        self.assert_widget(widget, response)


class WidgetsLanguageRedirectRenderTest(WidgetsRenderTest):
    def perform_test(self, widget: str, color: str) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": [*self.project.get_url_path(), "-", "cs"],
                    "widget": widget,
                    "color": color,
                    "extension": "svg",
                },
            ),
            follow=True,
        )

        self.assert_widget(widget, response)
