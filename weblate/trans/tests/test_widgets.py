# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for widgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.urls import reverse

from weblate.trans.models import Translation
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.widgets import WIDGETS

if TYPE_CHECKING:
    from django.http import HttpResponse


class WidgetsTest(FixtureTestCase):
    """Testing of widgets."""

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

    def test_view_engage_lang(self) -> None:
        response = self.client.get(
            reverse(
                "engage", kwargs={"path": [*self.project.get_url_path(), "-", "cs"]}
            )
        )
        self.assertContains(response, "Test")

    def test_site_og(self) -> None:
        response = self.client.get(reverse("og-image"))
        self.assert_png(response)


class WidgetsMeta(type):
    def __new__(mcs, name: str, bases: tuple[type], attrs: dict[str, Any]):
        def gen_test(widget: str, color: str):
            def test(self: WidgetsRenderTest) -> None:
                self.perform_test(widget, color)

            return test

        for widget in WIDGETS:
            for color in WIDGETS[widget].colors:
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
