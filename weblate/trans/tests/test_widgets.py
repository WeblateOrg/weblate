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

"""Test for widgets."""

from django.urls import reverse

from weblate.trans.models import Translation
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.widgets import WIDGETS


class WidgetsTest(FixtureTestCase):
    """Testing of widgets."""

    def test_view_widgets(self):
        response = self.client.get(reverse("widgets", kwargs=self.kw_project))
        self.assertContains(response, "Test")

    def test_view_widgets_lang(self):
        response = self.client.get(
            reverse("widgets", kwargs=self.kw_project), {"lang": "cs"}
        )
        self.assertContains(response, "Test")

    def test_view_engage(self):
        response = self.client.get(reverse("engage", kwargs=self.kw_project))
        self.assertContains(response, "Test")

    def test_view_engage_lang(self):
        response = self.client.get(reverse("engage", kwargs=self.kw_lang_project))
        self.assertContains(response, "Test")

    def test_site_og(self):
        response = self.client.get(reverse("og-image"))
        self.assert_png(response)


class WidgetsMeta(type):
    def __new__(mcs, name, bases, attrs):  # noqa
        def gen_test(widget, color):
            def test(self):
                self.perform_test(widget, color)

            return test

        for widget in WIDGETS:
            for color in WIDGETS[widget].colors:
                test_name = f"test_{widget}_{color}"
                attrs[test_name] = gen_test(widget, color)
        return type.__new__(mcs, name, bases, attrs)


class WidgetsRenderTest(FixtureTestCase, metaclass=WidgetsMeta):
    def assert_widget(self, widget, response):
        if hasattr(WIDGETS[widget], "redirect"):
            if hasattr(response, "redirect_chain"):
                self.assertEqual(response.redirect_chain[0][1], 301)
            else:
                self.assertEqual(response.status_code, 301)
        elif "svg" in WIDGETS[widget].content_type:
            self.assert_svg(response)
        else:
            self.assert_png(response)

    def perform_test(self, widget, color):
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "project": self.project.slug,
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsPercentRenderTest(WidgetsRenderTest):
    def perform_test(self, widget, color):
        for translated in (0, 3, 4):
            # Fake translated stats
            for translation in Translation.objects.iterator():
                translation.stats.store("translated", translated)
                translation.stats.save()
            response = self.client.get(
                reverse(
                    "widget-image",
                    kwargs={
                        "project": self.project.slug,
                        "widget": widget,
                        "color": color,
                        "extension": WIDGETS[widget].extension,
                    },
                )
            )

            self.assert_widget(widget, response)


class WidgetsComponentRenderTest(WidgetsRenderTest):
    def perform_test(self, widget, color):
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "project": self.project.slug,
                    "component": self.component.slug,
                    "widget": widget,
                    "color": color,
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsLanguageRenderTest(WidgetsRenderTest):
    def perform_test(self, widget, color):
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "project": self.project.slug,
                    "widget": widget,
                    "color": color,
                    "lang": "cs",
                    "extension": WIDGETS[widget].extension,
                },
            )
        )

        self.assert_widget(widget, response)


class WidgetsRedirectRenderTest(WidgetsRenderTest):
    def perform_test(self, widget, color):
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "project": self.project.slug,
                    "widget": widget,
                    "color": color,
                    "extension": "svg",
                },
            ),
            follow=True,
        )

        self.assert_widget(widget, response)


class WidgetsLanguageRedirectRenderTest(WidgetsRenderTest):
    def perform_test(self, widget, color):
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "project": self.project.slug,
                    "widget": widget,
                    "color": color,
                    "lang": "cs",
                    "extension": "svg",
                },
            ),
            follow=True,
        )

        self.assert_widget(widget, response)
