# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for widgets."""

from __future__ import annotations

from io import BytesIO
from math import ceil
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from PIL import Image

from weblate.fonts.render import (
    get_font_properties,
    measure_line,
    rendering_lock,
)
from weblate.trans.checklists import TranslationChecklistMixin
from weblate.trans.filter import FILTERS
from weblate.trans.models import Translation
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.views.widgets import WIDGETS
from weblate.trans.widgets import (
    PNG_BADGE_BASELINE,
    PNG_BADGE_FONT_SIZE,
    WIDGET_FONT,
    MatrixMultiLanguageWidget,
    NormalWidget,
    OpenGraphWidget,
    PNGBadgeWidget,
)
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.xml import parse_xml

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as ClientResponse


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
        self, response: ClientResponse, expected_urls: list[str]
    ) -> None:
        task_urls = [
            task.url for task in response.context["translate_object"].list_engage_tasks
        ]
        self.assertEqual(task_urls, expected_urls)

    def assert_engage_task_url(
        self, response: ClientResponse, expected_url: str
    ) -> None:
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
        self.assertEqual(Image.open(BytesIO(response.content)).size, (1200, 630))

    def test_open_graph_emphasizes_only_project_name(self) -> None:
        widget = OpenGraphWidget(self.project, "graph")

        with (
            patch("weblate.trans.widgets.gettext", return_value="Project {}"),
            patch("weblate.trans.widgets.draw_text") as mocked_draw_text,
            rendering_lock(),
        ):
            widget.render_additional(object())

        self.assertEqual(
            [call.args[3] for call in mocked_draw_text.call_args_list],
            ["Project ", str(self.project)],
        )
        self.assertEqual(
            [
                call.kwargs["font_properties"].get_weight()
                for call in mocked_draw_text.call_args_list
            ],
            [400, 700],
        )

    def test_open_graph_rtl_uses_visual_run_order(self) -> None:
        widget = OpenGraphWidget(self.project, "graph")

        with (
            patch("weblate.trans.widgets.get_language_bidi", return_value=True),
            patch("weblate.trans.widgets.gettext", return_value="מיזם {}"),
            patch("weblate.trans.widgets.draw_text") as mocked_draw_text,
            rendering_lock(),
        ):
            widget.render_additional(object())

        self.assertEqual(
            [call.args[3] for call in mocked_draw_text.call_args_list],
            [str(self.project), "מיזם "],
        )
        self.assertEqual(
            [
                call.kwargs["font_properties"].get_weight()
                for call in mocked_draw_text.call_args_list
            ],
            [700, 400],
        )
        self.assertGreater(
            mocked_draw_text.call_args_list[1].args[1],
            mocked_draw_text.call_args_list[0].args[1],
        )

    def test_png_badge_dimensions(self) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.project.get_url_path(),
                    "widget": "status",
                    "color": "badge",
                    "extension": "png",
                },
            )
        )

        self.assert_png(response)
        width, height = Image.open(BytesIO(response.content)).size
        self.assertGreater(width, 20)
        self.assertEqual(height, 20)

    def test_png_badge_measures_localized_label_with_rendered_font(self) -> None:
        request = RequestFactory().get("/")
        response = HttpResponse()
        widget = PNGBadgeWidget(self.project, "badge")
        translated_label = "மொழிபெயர்க்கப்பட்டது"

        with patch("weblate.trans.widgets.gettext", return_value=translated_label):
            label, value, _color = widget.get_badge_data(request)
            with rendering_lock():
                font_properties = get_font_properties(
                    WIDGET_FONT, size=PNG_BADGE_FONT_SIZE, weight=400
                )
                expected_width = ceil(
                    measure_line(f"   {label}   ", font_properties)[0]
                ) + ceil(measure_line(f"  {value}  ", font_properties)[0])
            widget.render(request, response)

        image = Image.open(BytesIO(response.content))

        self.assertEqual(image.width, expected_width)
        self.assertEqual(image.height, 20)

    def test_png_badge_preserves_pango_text_baseline(self) -> None:
        request = RequestFactory().get("/")
        response = HttpResponse()
        widget = PNGBadgeWidget(self.project, "badge")

        with patch("weblate.trans.widgets.draw_text") as mocked_draw_text:
            widget.render(request, response)

        self.assertEqual(
            [call.args[2] for call in mocked_draw_text.call_args_list],
            [PNG_BADGE_BASELINE + 1, PNG_BADGE_BASELINE] * 2,
        )

    def test_bitmap_widget_preserves_pango_text_baselines(self) -> None:
        request = RequestFactory().get("/")
        response = HttpResponse()
        widget = NormalWidget(self.project, "grey")

        with patch("weblate.trans.widgets.draw_text") as mocked_draw_text:
            widget.render(request, response)

        self.assertEqual(
            [call.args[2] for call in mocked_draw_text.call_args_list],
            [31, 53, 31, 53, 31, 53],
        )
        self.assertTrue(
            all(
                call.kwargs["verticalalignment"] == "baseline"
                for call in mocked_draw_text.call_args_list
            )
        )


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
    def assert_widget(self, widget: str, response: ClientResponse) -> None:
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


class MatrixWidgetTest(FixtureTestCase):
    def test_matrix_columns_avoid_dangling_rows(self) -> None:
        widget = WIDGETS["matrix"](self.project, "auto")
        assert isinstance(widget, MatrixMultiLanguageWidget)

        self.assertEqual(widget.get_column_count(5, 100), 5)
        self.assertEqual(widget.get_column_count(5, 180), 3)
        self.assertEqual(widget.get_column_count(7, 130), 4)
        self.assertEqual(widget.get_column_count(13, 130), 5)

    def test_matrix_component_uses_translation_links(self) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.component.get_url_path(),
                    "widget": "matrix",
                    "color": "auto",
                    "extension": "svg",
                },
            )
        )

        self.assert_svg(response)
        content = response.content.decode()
        translation_url = reverse(
            "translate", kwargs={"path": [*self.component.get_url_path(), "de"]}
        )
        self.assertIn(
            f'xlink:href="http://example.com{translation_url}"',
            content,
        )
        self.assertNotIn("/test/test/-/de/", content)

    def test_matrix_uses_language_names_and_progress_bars(self) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.project.get_url_path(),
                    "widget": "matrix",
                    "color": "auto",
                    "extension": "svg",
                },
            )
        )

        self.assert_svg(response)
        content = response.content.decode()
        self.assertIn(">German</text>", content)
        self.assertNotIn(">de</text>", content)

        tree = parse_xml(response.content)
        progress_bars = [
            element
            for element in tree.findall(".//{http://www.w3.org/2000/svg}rect")
            if element.attrib.get("fill-opacity") == ".24"
        ]
        self.assertGreater(len(progress_bars), 0)
        self.assertTrue(
            any(int(element.attrib["width"]) > 5 for element in progress_bars)
        )


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


class WidgetsCapitalizeTest(FixtureTestCase):
    def test_capitalize_parameter(self) -> None:
        response = self.client.get(
            reverse(
                "widget-image",
                kwargs={
                    "path": self.project.get_url_path(),
                    "widget": "svg",
                    "color": "badge",
                    "extension": "svg",
                },
            ),
            {"capitalize": "1"},
        )
        self.assertContains(response, ">Translated<")
