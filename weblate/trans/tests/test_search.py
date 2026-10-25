# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for search views."""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import ANY, patch
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import connection
from django.http import QueryDict
from django.template import Context
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils.html import escape
from lxml import html

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import Group, Role, User
from weblate.checks.models import Check
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.bulk import bulk_perform
from weblate.trans.forms import AutoForm, BulkEditForm
from weblate.trans.models import (
    Change,
    Comment,
    Component,
    PendingUnitChange,
    Project,
    Translation,
    Unit,
    WorkflowSetting,
)
from weblate.trans.templatetags.translations import get_translate_url
from weblate.trans.tests.test_views import ReusableViewTestCase
from weblate.utils.forms import SearchField
from weblate.utils.ratelimit import reset_rate_limit
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import get_form_data
from weblate.workspaces.models import Workspace


class SearchViewTest(ReusableViewTestCase):
    CREATE_GLOSSARIES = True

    def setUp(self) -> None:
        super().setUp()
        self.translation = self.component.translation_set.get(language_code="cs")
        self.translate_url = self.translation.get_translate_url()
        self.update_fulltext_index()
        reset_rate_limit("search", address="127.0.0.1")

    def do_search(self, params, expected, url=None, *, anchor="#search"):
        """Perform search test."""
        if url is None:
            url = self.translate_url
        response = self.client.get(url, params)
        if expected is None:
            extra = ""
            if "q" in params:
                extra = f"?q={params['q']}"
            self.assertRedirects(
                response, f"{self.translation.get_absolute_url()}{extra}{anchor}"
            )
        else:
            self.assertContains(response, expected)
        return response

    def make_fake_page(
        self,
        *,
        count: int,
        num_pages: int = 1,
        per_page: int = 20,
        has_previous: bool = False,
        has_next: bool = False,
    ):
        class FakePage:
            def __init__(self) -> None:
                self.object_list = ()
                self.number = 1
                self.paginator = SimpleNamespace(
                    count=count,
                    num_pages=num_pages,
                    per_page=per_page,
                    sort_by=None,
                )
                self.has_previous = has_previous
                self.has_next = has_next

            def __iter__(self):
                return iter(self.object_list)

        return FakePage()

    def do_search_url(self, url) -> None:
        """Test search on given URL."""
        response = self.client.get(url, {"q": "hello"})
        self.assertContains(response, '<span class="hlmatch">Hello</span>, world')
        response = self.client.get(url, {"q": "changed:>=2010-01-10"})
        self.assertContains(response, "2010-01-10")

    def get_search_result_count(self, query: str) -> int:
        response = self.client.get(
            reverse("search", kwargs={"path": self.translation.get_url_path()}),
            {"q": query},
        )
        self.assertEqual(response.status_code, 200)
        return response.context["total_strings"]

    @override_settings(RATELIMIT_SEARCH_ATTEMPTS=20000)
    def test_all_search(self) -> None:
        """Searching in all projects."""
        response = self.client.get(reverse("search"), {"q": "hello"})
        self.assertContains(response, '<span class="hlmatch">Hello</span>, world')
        response = self.client.get(reverse("search"), {"q": 'source:r"^Hello"'})
        self.assertContains(response, "Hello, world")
        response = self.client.get(reverse("search"), {"q": 'source:r"^(Hello"'})
        self.assertContains(response, "Invalid regular expression")
        response = self.client.get(
            reverse("search"), {"q": "hello AND state:<translated"}
        )
        self.assertContains(response, "Hello, world")
        response = self.client.get(reverse("search"), {"q": "hello AND state:empty"})
        self.assertContains(response, "Hello, world")
        response = self.client.get(reverse("search"), {"q": "check:php_format"})
        self.assertContains(response, "No matching strings found.")
        response = self.client.get(
            reverse("search"), {"q": "check:php_format", "ignored": "1"}
        )
        self.assertContains(response, "No matching strings found.")
        self.do_search_url(reverse("search"))

    @override_settings(RATELIMIT_SEARCH_ATTEMPTS=20000)
    def test_bulk_edit_selection_rendering(self) -> None:
        url = reverse("search", kwargs={"path": self.translation.get_url_path()})

        # No bulk edit permission
        response = self.client.get(url, {"q": "hello"})
        self.assertNotContains(response, 'id="bulk-edit-form"')

        self.make_manager()
        response = self.client.get(url, {"q": "hello"})
        self.assertContains(response, 'id="bulk-edit-form"')
        self.assertContains(response, "bulk-edit-select")
        self.assertContains(response, "bulk-edit-toggle-selection")
        # The selection is posted as a single field, the checkboxes themselves
        # are not part of the form, see test_bulk_edit_selected_units_single_field
        self.assertContains(response, 'id="bulk-edit-selected-units"')
        self.assertNotContains(response, 'form="bulk-edit-form"')
        bulk_form = response.context["bulk_state_form"]
        self.assertFalse(bulk_form.fields["q"].required)
        self.assertIn("units", bulk_form.fields)
        # The form is rendered without a crispy form tag, it still has to
        # include the CSRF token to be submittable
        form_html = re.search(
            r'<form id="bulk-edit-form".*?</form>',
            response.content.decode(),
            re.DOTALL,
        )
        assert form_html is not None
        self.assertIn("csrfmiddlewaretoken", form_html.group(0))
        # One field for the whole selection, not one per listed string
        response = self.client.get(url, {"q": "state:empty"})
        content = response.content.decode()
        self.assertGreater(content.count('bulk-edit-select"'), 1)
        self.assertEqual(content.count('name="units"'), 1)

        # Not offered for scopes which do not support bulk edit
        response = self.client.get(reverse("search"), {"q": "hello"})
        self.assertNotContains(response, 'id="bulk-edit-form"')
        response = self.client.get(
            reverse(
                "search",
                kwargs={"path": self.translation.language.get_url_path()},
            ),
            {"q": "hello"},
        )
        self.assertNotContains(response, 'id="bulk-edit-form"')

    def test_pagination(self) -> None:
        response = self.client.get(reverse("search"), {"q": "hello", "page": "1"})
        self.assertContains(response, '<span class="hlmatch">Hello</span>, world')
        response = self.client.get(reverse("search"), {"q": "hello", "page": "10"})
        self.assertContains(response, '<span class="hlmatch">Hello</span>, world')
        response = self.client.get(reverse("search"), {"q": "hello", "page": "x"})
        self.assertContains(response, '<span class="hlmatch">Hello</span>, world')

    def test_scoped_listing(self) -> None:
        workspace = Workspace.objects.create(name="Search workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save(update_fields=["category"])
        language = self.translation.language
        for obj in (
            workspace,
            self.project,
            category,
            self.component,
            language,
            self.translation,
            ProjectLanguage(self.project, language),
            CategoryLanguage(category, language),
        ):
            with self.subTest(obj=obj):
                response = self.client.get(
                    reverse("search", kwargs={"path": obj.get_url_path()})
                )
                self.assertContains(response, "Hello, world!")
                self.assertTrue(response.context["show_results"])
                self.assertEqual(response.context["title"], "All strings")

    def test_global_landing(self) -> None:
        response = self.client.get(reverse("search"))
        self.assertNotIn("show_results", response.context)
        response = self.client.get(reverse("search"), {"q": ""})
        self.assertTrue(response.context["show_results"])

    def test_listing_pagination_and_editor_links(self) -> None:
        source_unit = self.get_unit().source_unit
        Unit.objects.bulk_create(
            [
                Unit(
                    translation=self.translation,
                    id_hash=-10_000_000 - index,
                    source=f"Page source {index:02}",
                    target=f"Page target {index:02}",
                    position=10_000 + index,
                    source_unit=source_unit,
                )
                for index in range(25)
            ]
        )
        url = reverse("search", kwargs=self.kw_translation)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                url, {"sort_by": "-source", "limit": "10", "page": "2"}
            )
        page = response.context["page_obj"]
        self.assertEqual(page.number, 2)
        self.assertEqual(len(page.object_list), 10)
        self.assertTrue(
            any(
                'FROM "trans_unit"' in query["sql"]
                and "LIMIT 10 OFFSET 10" in query["sql"]
                for query in queries
            )
        )
        self.assertEqual(
            list(page.object_list),
            list(self.translation.unit_set.order_by("-source")[10:20]),
        )
        self.assertEqual(
            response.context["total_strings"], self.translation.unit_set.count()
        )
        unit = page.object_list[0]
        self.assertContains(
            response,
            f"{self.translate_url}?sort_by=-source&amp;checksum={unit.checksum}",
        )
        self.assertContains(response, "sort-up")
        self.assertNotContains(response, "/browse/")

    def test_source_listing(self) -> None:
        response = self.client.get(
            reverse(
                "search",
                kwargs={"path": self.component.source_translation.get_url_path()},
            )
        )
        self.assertContains(response, "Hello, world!")
        self.assertNotContains(response, "<th>Source string</th>")
        self.assertNotContains(response, "<th>Translation</th>")

    def test_glossary_listing(self) -> None:
        glossary = self.project.glossaries[0].translation_set.get(
            language=self.translation.language
        )
        url = reverse("search", kwargs={"path": glossary.get_url_path()})
        self.assertEqual(get_translate_url(Context({"user": self.user}), glossary), url)
        response = self.client.get(url)
        self.assertTrue(response.context["show_results"])
        self.assertEqual(response.context["search_form"].sort_query, "source")
        self.assertContains(response, f"{glossary.get_absolute_url()}#new")
        self.client.logout()
        response = self.client.get(url)
        self.assertNotContains(response, f"{glossary.get_absolute_url()}#new")

    def test_browse_redirect(self) -> None:
        url = reverse("browse", kwargs=self.kw_translation)
        target = reverse("search", kwargs=self.kw_translation)
        self.assertRedirects(self.client.get(url), target, status_code=301)
        for params, expected in (
            ({"offset": "3"}, {"page": "3", "limit": "20"}),
            ({"offset": "bad"}, {"page": "1", "limit": "20"}),
            ({"offset": "-1"}, {"page": "1", "limit": "20"}),
            (
                {"offset": "3", "page": "2", "limit": "10"},
                {"page": "2", "limit": "10"},
            ),
        ):
            with self.subTest(params=params):
                params.update({"q": 'source:"Hello, world!"', "sort_by": "-source"})
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 301)
                location = urlsplit(response.headers["Location"])
                self.assertEqual(location.path, target)
                expected.update({"q": params["q"], "sort_by": "-source"})
                self.assertEqual(QueryDict(location.query).dict(), expected)
        response = self.client.get(f"{url}?q=hello&extra=a&extra=b")
        self.assertEqual(
            QueryDict(urlsplit(response.headers["Location"]).query).getlist("extra"),
            ["a", "b"],
        )

    def test_scoped_translate_action(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save(update_fields=["category"])
        for obj in (
            self.translation,
            ProjectLanguage(self.project, self.translation.language),
            CategoryLanguage(category, self.translation.language),
        ):
            with self.subTest(obj=obj):
                path = obj.get_url_path()
                response = self.client.get(
                    reverse("search", kwargs={"path": path}),
                    {"q": "hello", "sort_by": "-source", "page": "2", "offset": "3"},
                )
                location = urlsplit(response.context["translate_url"])
                self.assertEqual(
                    location.path, reverse("translate", kwargs={"path": path})
                )
                self.assertEqual(
                    QueryDict(location.query).dict(),
                    {"q": "hello", "sort_by": "-source"},
                )
                self.assertContains(response, "Translate</a>")
        response = self.client.get(reverse("search", kwargs=self.kw_component))
        self.assertNotIn("translate_url", response.context)

    def test_scoped_widget_links(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save(update_fields=["category"])
        language = self.translation.language
        for obj, component in (
            (self.translation, self.component),
            (ProjectLanguage(self.project, language), None),
            (CategoryLanguage(category, language), None),
        ):
            with self.subTest(obj=obj):
                response = self.client.get(
                    reverse("search", kwargs={"path": obj.get_url_path()})
                )
                widget_url = obj.get_widgets_url()
                badge_links = re.findall(
                    r'<a href="([^"]+)">\s*<img[^>]+alt="Translation status widgets"',
                    response.content.decode(),
                )
                self.assertEqual(badge_links, [escape(widget_url)])
                response = self.client.get(widget_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["form"].cleaned_data["lang"], language
                )
                self.assertEqual(
                    response.context["form"].cleaned_data["component"], component
                )

    def test_invalid_scoped_query(self) -> None:
        response = self.client.get(
            reverse("search", kwargs=self.kw_translation), {"q": 'source:r"^(Hello"'}
        )
        self.assertContains(response, "Invalid regular expression")
        self.assertNotIn("show_results", response.context)
        self.assertNotIn("translate_url", response.context)
        self.assertNotContains(response, "Hello, world!")

    def test_scoped_listing_rate_limit(self) -> None:
        with patch("weblate.trans.views.search.check_rate_limit", return_value=False):
            response = self.client.get(reverse("search", kwargs=self.kw_translation))
        self.assertContains(response, "Too many search queries")
        self.assertNotIn("show_results", response.context)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_private_scoped_listing(self) -> None:
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        self.client.logout()
        response = self.client.get(reverse("search", kwargs=self.kw_translation))
        self.assertNotEqual(response.status_code, 200)
        response = self.client.get(reverse("search"), {"q": "hello"})
        self.assertNotContains(response, "Hello, world!")

    def test_language_search(self) -> None:
        """Searching in all projects."""
        response = self.client.get(reverse("search"), {"q": "hello", "lang": "cs"})
        self.assertContains(response, '<span class="hlmatch">Hello</span>, world')

    def test_project_search(self) -> None:
        """Searching within project."""
        self.do_search_url(
            reverse("search", kwargs={"path": self.project.get_url_path()})
        )

    def test_workspace_search(self) -> None:
        """Searching within workspace."""
        workspace = Workspace.objects.create(name="Search workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])

        self.do_search_url(reverse("search", kwargs={"path": workspace.get_url_path()}))

    def test_workspace_bulk_edit(self) -> None:
        """Bulk editing within workspace."""
        workspace = Workspace.objects.create(name="Bulk workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.user.clear_permissions_cache()

        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": workspace.get_url_path()}),
            {
                "q": "source:Hello",
                "state": STATE_TRANSLATED,
                "add_flags": "",
                "remove_flags": "",
            },
            follow=True,
        )

        self.assertContains(response, "Bulk edit completed")

    def test_workspace_bulk_edit_derives_matching_components(self) -> None:
        """Bulk editing within workspace derives affected components from matches."""
        workspace = Workspace.objects.create(name="Bulk workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.user.clear_permissions_cache()

        with patch(
            "weblate.trans.views.search.bulk_perform", return_value=0
        ) as perform:
            response = self.client.post(
                reverse("bulk-edit", kwargs={"path": workspace.get_url_path()}),
                {
                    "q": "source:Hello",
                    "state": STATE_TRANSLATED,
                    "add_flags": "",
                    "remove_flags": "",
                },
                follow=True,
            )

        self.assertContains(response, "Bulk edit completed")
        self.assertIsNone(perform.call_args.kwargs["components"])

    def test_component_search(self) -> None:
        """Searching within component."""
        self.do_search_url(reverse("search", kwargs=self.kw_component))

    def test_project_language_search(self) -> None:
        """Searching within project."""
        self.do_search_url(
            reverse("search", kwargs={"path": [self.project.slug, "-", "cs"]})
        )

    def test_project_search_skips_large_word_summary(self) -> None:
        with (
            patch(
                "weblate.trans.views.search.get_paginator",
                return_value=self.make_fake_page(count=1_001),
            ),
            patch("weblate.trans.views.search.fill_in_source_translation"),
            patch(
                "weblate.trans.models.unit.UnitQuerySet.aggregate",
                side_effect=AssertionError(
                    "large search summary should not aggregate total words"
                ),
            ),
        ):
            response = self.client.get(
                reverse("search", kwargs={"path": self.project.get_url_path()}),
                {"q": "hello"},
            )

        self.assertEqual(response.context["total_strings"], 1_001)
        self.assertIsNone(response.context["total_words"])

    def test_project_search_word_summary_uses_full_queryset(self) -> None:
        with (
            patch(
                "weblate.trans.views.search.get_paginator",
                return_value=self.make_fake_page(
                    count=10, num_pages=2, per_page=5, has_next=True
                ),
            ),
            patch("weblate.trans.views.search.fill_in_source_translation"),
            patch(
                "weblate.trans.models.unit.UnitQuerySet.aggregate",
                return_value={"total_words": 123},
            ) as aggregate,
        ):
            response = self.client.get(
                reverse("search", kwargs={"path": self.project.get_url_path()}),
                {"q": "hello"},
            )

        aggregate.assert_called_once_with(total_words=ANY)
        self.assertEqual(response.context["total_strings"], 10)
        self.assertEqual(response.context["total_words"], 123)

    def test_translation_search(self) -> None:
        """Searching within translation."""
        # Default
        self.do_search({"q": "source:hello"}, "source:hello")
        # Short exact
        self.do_search({"q": "x", "search": "exact"}, None)

    def test_comment_search_keeps_source_comments_separate(self) -> None:
        unit = self.get_unit()
        Comment.objects.all().delete()

        Comment.objects.create(
            unit=unit.source_unit,
            comment="Source comment by me",
            user=self.user,
        )

        self.assertEqual(self.get_search_result_count('comment_author:="testuser"'), 0)
        self.assertEqual(self.get_search_result_count("has:comment"), 0)
        self.assertEqual(
            self.get_search_result_count('source_comment_author:="testuser"'), 1
        )
        self.assertEqual(self.get_search_result_count("has:source-comment"), 1)

        Comment.objects.create(
            unit=unit,
            comment="Translation comment by me",
            user=self.user,
        )

        self.assertEqual(self.get_search_result_count('comment_author:="testuser"'), 1)
        self.assertEqual(self.get_search_result_count("has:comment"), 1)

    def test_related_search_totals(self) -> None:
        unit = self.get_unit()
        Comment.objects.bulk_create(
            [Comment(unit=unit, user=self.user, comment="alpha") for _ in range(3)]
        )
        for path in (
            None,
            self.project.get_url_path(),
            self.translation.get_url_path(),
        ):
            with self.subTest(path=path):
                url = reverse("search", kwargs={"path": path} if path else None)
                response = self.client.get(
                    url,
                    {"q": f"id:{unit.pk} AND comment:alpha", "sort_by": "num_comments"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["total_strings"], 1)
                self.assertEqual(response.context["total_words"], unit.num_words)
                self.assertEqual(
                    [result.pk for result in response.context["page_obj"]], [unit.pk]
                )
                self.assertFalse(
                    response.context["page_obj"].paginator.object_list.query.distinct
                )

    def test_mass_action_filters_require_a_query(self) -> None:
        for form in (
            AutoForm(self.component, user=self.user),
            BulkEditForm(self.user, self.translation),
        ):
            with self.subTest(form=type(form).__name__):
                choices = SearchField("q").get_search_query_choices(form)
                self.assertNotIn("all", [choice[0] for choice in choices])
                self.assertTrue(all(choice[2] for choice in choices))
                self.assertIn("translated", [choice[0] for choice in choices])
                # Use the bound field's requirement, including runtime overrides.
                form.fields["q"].required = False
                choices = SearchField("q").get_search_query_choices(form)
                self.assertEqual(choices[0][:3], ("all", "All strings", ""))

    def test_search_filter_dropdown_includes_comments_by_me(self) -> None:
        response = self.client.get(
            reverse("search", kwargs={"path": self.translation.get_url_path()})
        )

        self.assertContains(response, "Strings with comments by me")
        self.assertContains(response, "comment_author:=&quot;testuser&quot;")
        self.assertContains(response, "Strings with source comments by me")
        self.assertContains(response, "source_comment_author:=&quot;testuser&quot;")

    def test_review(self) -> None:
        # Review
        self.do_search({"q": "changed:>=2010-01-10"}, None)
        self.do_search({"q": "changed:>=2010-01-10 AND NOT changed_by:testuser"}, None)
        self.do_search({"q": "changed:>2010-01-10 AND changed_by:testuser"}, None)
        self.do_search({"q": "changed_by:testuser"}, None)
        # Review, partial date
        self.do_search({"q": "changed:>=2010-01-"}, None)

    def extract_params(self, response):
        search_url = re.findall(r'data-params="([^"]*)"', response.content.decode())[0]
        return QueryDict(search_url, mutable=True)

    def test_search_links(self) -> None:
        response = self.do_search({"q": "source:Weblate"}, "source:Weblate")
        # Extract search URL
        params = self.extract_params(response)
        # Try access to pages
        params["offset"] = 1
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, "https://demo.weblate.org/")
        params["offset"] = 2
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, "Thank you for using Weblate.")
        # Invalid offset
        params["offset"] = "bug"
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, "https://demo.weblate.org/")
        # Go to end
        params["offset"] = 3
        response = self.client.get(self.translate_url, params)
        self.assertRedirects(response, self.translation.get_absolute_url())
        # Try no longer cached query (should be deleted above)
        params["offset"] = 2
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, "Thank you for using Weblate.")

    def test_search_checksum(self) -> None:
        unit = self.translation.unit_set.get(
            source="Try Weblate at <https://demo.weblate.org/>!\n"
        )
        self.do_search({"checksum": unit.checksum}, "3 / 4")

    def test_search_offset(self) -> None:
        """Test offset navigation."""
        self.do_search({"offset": 1}, "1 / 4")
        self.do_search({"offset": 4}, "4 / 4")
        self.do_search({"offset": 5}, None, anchor="")

    def test_search_type(self) -> None:
        self.do_search({"q": "state:<translated"}, "Unfinished strings")
        self.do_search({"q": "state:needs-editing"}, None)
        self.do_search({"q": "has:suggestion"}, None)
        self.do_search({"q": "has:check"}, None)
        self.do_search({"q": "check:plurals"}, None)
        self.do_search({"q": ""}, "1 / 4")

    def test_search_automatically_translated(self) -> None:
        self.do_search({"q": "is:automatically-translated"}, None)

        unit = self.translation.unit_set.first()
        assert unit is not None
        unit.automatically_translated = True
        unit.save()

        response = self.do_search({"q": "is:automatically-translated"}, "1 / 1")
        self.assertContains(response, unit.source)

        self.do_search({"q": "NOT is:automatically-translated"}, "1 / 3")

    def test_search_plural(self) -> None:
        response = self.do_search({"q": "banana"}, "banana")
        self.assertContains(response, "One")
        self.assertContains(response, "Few")
        self.assertContains(response, "Other")
        self.assertNotContains(response, "Plural form ")

    def assert_search_variant(
        self,
        expected_source: str,
        match_components: list[Translation],
        no_match_component: Translation,
    ) -> None:
        for component in match_components:
            response = self.client.get(
                reverse("search", kwargs={"path": component.get_url_path()}),
                {"q": "has:variant"},
            )
            self.assertContains(response, expected_source)

        response = self.client.get(
            reverse("search", kwargs={"path": no_match_component.get_url_path()}),
            {"q": "has:variant"},
        )
        self.assertContains(response, "No matching strings found.")

    def test_search_variant_with_flag_create(self) -> None:
        """
        Test glossary variant search.

        Specifically checks that search result of 'has:variant' only contains
        units that have variants in the search language
        """
        self.glossary = self.project.glossaries[0]
        en_glossary = self.glossary.translation_set.get(language__code="en")  # source
        de_glossary = self.glossary.translation_set.get(language__code="de")
        cs_glossary = self.glossary.translation_set.get(language__code="cs")

        en_glossary.add_unit(None, "", source="glossary-term", author=self.user)

        # create a unit with a variant for both 'en' and 'de'
        de_glossary.add_unit(
            None,
            "",
            source="variant-glossary-term",
            extra_flags="variant:glossary-term",
            author=self.user,
        )

        self.assert_search_variant(
            "variant-glossary-term", [en_glossary, de_glossary], cs_glossary
        )

    def test_search_variant_with_regex_key(self) -> None:
        mono_component = self.create_po_mono(project=self.project, name="Monolingual")

        # set variant_regex match
        url = reverse("settings", kwargs={"path": mono_component.get_url_path()})
        self.project.add_user(self.user, "Administration")
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data["variant_regex"] = r"(_variant)$"

        response = self.client.post(
            url,
            data,
            follow=True,
        )
        self.assertContains(response, "Settings saved")

        mono_component.refresh_from_db()
        self.assertNotEqual(mono_component.variant_regex, "")

        en_glossary = mono_component.translation_set.get(language__code="en")  # source
        de_glossary = mono_component.translation_set.get(language__code="de")
        cs_glossary = mono_component.translation_set.get(language__code="cs")

        en_glossary.add_unit(None, "original", "glossary-term", author=self.user)
        de_glossary.add_unit(
            None, "original_variant", source="variant-glossary-term", author=self.user
        )

        self.assert_search_variant(
            "glossary-term", [en_glossary, de_glossary], cs_glossary
        )

    def test_checksum(self) -> None:
        self.do_search({"checksum": "invalid"}, None, anchor="")

    def test_search_multiple_labels(self) -> None:
        """Test that searching with label:ABC AND label:XYZ works correctly."""
        label1 = self.project.label_set.create(name="ABC", color="black")
        label2 = self.project.label_set.create(name="XYZ", color="blue")

        unit = self.get_unit()
        source_unit = unit.source_unit
        source_unit.labels.add(label1, label2)

        unit.translation.stats.clear()

        self.do_search({"q": "label:ABC"}, "Hello, world!")
        self.do_search({"q": "label:XYZ"}, "Hello, world!")
        self.do_search({"q": "label:ABC AND label:XYZ"}, "Hello, world!")
        self.do_search({"q": "label:ABC label:XYZ"}, "Hello, world!")

        source_unit.labels.remove(label2)
        unit.translation.stats.clear()
        self.do_search({"q": "label:ABC AND label:XYZ"}, None)
        self.do_search({"q": "label:ABC label:XYZ"}, None)

    def test_search_multiple_checks(self) -> None:
        """Test that searching with check:A AND check:B works correctly."""
        unit = self.get_unit()
        Check.objects.create(unit=unit, name="ellipsis", dismissed=False)
        Check.objects.create(unit=unit, name="same", dismissed=False)

        self.do_search({"q": "check:ellipsis"}, "Hello, world!")
        self.do_search({"q": "check:same"}, "Hello, world!")
        self.do_search({"q": "check:ellipsis AND check:same"}, "Hello, world!")
        self.do_search({"q": "check:ellipsis check:same"}, "Hello, world!")

        Check.objects.filter(unit=unit, name="same").update(dismissed=True)
        self.do_search(
            {"q": "check:ellipsis AND dismissed_check:same"}, "Hello, world!"
        )
        self.do_search({"q": "check:ellipsis dismissed_check:same"}, "Hello, world!")

        Check.objects.filter(unit=unit, name="same").delete()
        self.do_search({"q": "check:ellipsis AND check:same"}, None)
        self.do_search({"q": "check:ellipsis check:same"}, None)

    def test_search_multiple_screenshots(self) -> None:
        """Test that searching with screenshot:A AND screenshot:B works correctly."""
        unit = self.get_unit()
        source_unit = unit.source_unit
        translation = self.component.source_translation

        shot1 = Screenshot.objects.create(
            name="ScreenshotAlpha", translation=translation
        )
        shot2 = Screenshot.objects.create(
            name="ScreenshotBeta", translation=translation
        )
        shot1.units.add(source_unit)
        shot2.units.add(unit)

        self.do_search({"q": "screenshot:ScreenshotAlpha"}, "Hello, world!")
        self.do_search({"q": "screenshot:ScreenshotBeta"}, "Hello, world!")
        self.do_search(
            {"q": "screenshot:ScreenshotAlpha AND screenshot:ScreenshotBeta"},
            "Hello, world!",
        )
        self.do_search(
            {"q": "screenshot:ScreenshotAlpha screenshot:ScreenshotBeta"},
            "Hello, world!",
        )

        shot2.units.remove(unit)
        self.do_search(
            {"q": "screenshot:ScreenshotAlpha AND screenshot:ScreenshotBeta"}, None
        )
        self.do_search(
            {"q": "screenshot:ScreenshotAlpha screenshot:ScreenshotBeta"}, None
        )


class ReplaceTest(ReusableViewTestCase):
    """Test for search and replace functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.unit = self.get_unit()
        self.make_manager()

    def confirm_preview(self, response, url, units=None, *, apply_all=False):
        return self.client.post(
            url,
            {
                "bulk_confirmation": response.context["confirmation"],
                "preview_units": [] if units is None else units,
                **({"apply_all": "1"} if apply_all else {}),
            },
            follow=True,
        )

    def do_replace_test(self, url, confirm=True, query=None) -> None:
        query = query or ""
        response = self.client.post(
            url, {"q": query, "search": "Nazdar", "replacement": "Ahoj"}, follow=True
        )
        self.assertContains(response, "Review and confirm the bulk edit changes.")
        response = self.confirm_preview(
            response, url, [self.unit.pk] if confirm else []
        )
        unit = self.get_unit()
        if confirm:
            self.assertContains(response, "Bulk edit completed, 1 string was updated.")
            self.assertEqual(unit.target, "Ahoj svete!\n")
        else:
            self.assertContains(
                response, "Bulk edit completed, no strings were updated."
            )
            self.assertEqual(unit.target, "Nazdar svete!\n")

    def test_no_match(self) -> None:
        response = self.client.post(
            reverse("replace", kwargs=self.kw_translation),
            {"search": "Ahoj", "replacement": "Cau"},
            follow=True,
        )
        self.assertEqual(response.context["total"], 0)
        unit = self.get_unit()
        self.assertEqual(unit.target, "Nazdar svete!\n")

    def test_replace_translated(self) -> None:
        self.do_replace_test(
            reverse("replace", kwargs=self.kw_translation),
            "is:translated",
        )

    def test_replace_nontranslated(self) -> None:
        response = self.client.post(
            reverse("replace", kwargs=self.kw_translation),
            {"q": "NOT is:translated", "search": "Nazdar", "replacement": "Ahoj"},
            follow=True,
        )
        self.assertEqual(response.context["total"], 0)

    def test_replace(self) -> None:
        self.do_replace_test(reverse("replace", kwargs=self.kw_translation))

    def test_replace_initial_action(self) -> None:
        response = self.client.get(self.component.get_absolute_url())

        self.assertContains(response, 'id="id_bulk_preview"')
        self.assertNotContains(response, 'value="Replace"')
        self.assertNotContains(response, "Don’t worry about messing up the strings.")

    def test_replace_preview_parameters_are_editable(self) -> None:
        url = reverse("replace", kwargs=self.kw_translation)

        response = self.client.post(
            url,
            {"q": "", "search": "Nazdar", "replacement": "Ahoj"},
            follow=True,
        )

        self.assertContains(response, "Review and confirm the bulk edit changes.")
        self.assertContains(response, "Update preview")
        self.assertContains(response, ">Apply</button>")
        self.assertContains(response, 'id="id_bulk_search"')
        self.assertContains(response, 'id="id_bulk_replacement"')
        content = response.content.decode()
        self.assertEqual(content.count('id="id_bulk_search"'), 1)
        self.assertEqual(content.count('id="id_bulk_replacement"'), 1)

        response = self.client.post(
            url,
            {"q": "", "search": "Nazdar", "replacement": "Cau"},
            follow=True,
        )

        unit = self.get_unit()
        self.assertContains(response, "Review and confirm the bulk edit changes.")
        self.assertContains(response, 'value="Cau"')
        self.assertEqual(unit.target, "Nazdar svete!\n")

        response = self.confirm_preview(response, url, [self.unit.pk])

        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        unit = self.get_unit()
        self.assertEqual(unit.target, "Cau svete!\n")

    def test_replace_project(self) -> None:
        self.do_replace_test(
            reverse("replace", kwargs={"path": self.project.get_url_path()})
        )

    def test_replace_workspace(self) -> None:
        workspace = Workspace.objects.create(name="Replace workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#bulk-edit"')
        self.do_replace_test(
            reverse("replace", kwargs={"path": workspace.get_url_path()})
        )

    def test_replace_workspace_excludes_other_workspaces(self) -> None:
        workspace = Workspace.objects.create(name="Replace workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        outside_project = self.create_project(
            name="Outside workspace",
            slug="outside-workspace",
        )
        outside_component = self.create_po(
            project=outside_project,
            name="Outside component",
        )
        outside_unit = outside_component.translation_set.get(
            language_code="cs"
        ).unit_set.get(source__startswith="Hello, world!")
        outside_unit.translate(
            self.user,
            "Nazdar outside!\n",
            STATE_TRANSLATED,
        )
        url = reverse("replace", kwargs={"path": workspace.get_url_path()})

        response = self.client.post(
            url,
            {"q": "", "search": "Nazdar", "replacement": "Ahoj"},
        )

        self.assertContains(response, "Review and confirm the bulk edit changes.")
        self.assertNotContains(response, outside_component.name)

        response = self.confirm_preview(response, url, [self.unit.pk])

        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        outside_unit.refresh_from_db()
        self.assertEqual(outside_unit.target, "Nazdar outside!\n")

    def test_replace_workspace_requires_edit_permission(self) -> None:
        workspace = Workspace.objects.create(name="Read-only replace workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.user.groups.clear()
        group = Group.objects.create(
            name="Workspace project access",
            language_selection=SELECTION_ALL,
        )
        group.projects.add(self.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        url = reverse("replace", kwargs={"path": workspace.get_url_path()})

        response = self.client.get(workspace.get_absolute_url())

        self.assertNotContains(response, "Search and replace", status_code=200)

        response = self.client.post(
            url,
            {"q": "", "search": "Nazdar", "replacement": "Ahoj"},
        )

        self.assertEqual(response.status_code, 403)

    def test_replace_workspace_caps_editable_units(self) -> None:
        workspace = Workspace.objects.create(name="Mixed access workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        Unit.objects.bulk_create(
            [
                Unit(
                    translation=self.translation,
                    id_hash=-10_000_000 - index,
                    source=f"View-only source {index}",
                    target="Nazdar view-only",
                    state=STATE_TRANSLATED,
                    original_state=STATE_TRANSLATED,
                    position=10_000 + index,
                    source_unit=self.unit.source_unit,
                )
                for index in range(249)
            ]
        )
        editable_project = self.create_project(
            name="Editable workspace project",
            slug="editable-workspace-project",
            workspace=workspace,
        )
        editable_component = self.create_po(
            project=editable_project,
            name="editable-workspace-component",
        )
        editable_unit = editable_component.translation_set.get(
            language_code="cs"
        ).unit_set.get(source__startswith="Hello, world!")
        editable_unit.translate(
            self.user,
            "Nazdar editable\n",
            STATE_TRANSLATED,
        )

        self.user.groups.clear()
        view_group = Group.objects.create(
            name="View-only workspace project",
            language_selection=SELECTION_ALL,
        )
        view_group.projects.add(self.project)
        edit_group = Group.objects.create(
            name="Editable workspace project",
            language_selection=SELECTION_ALL,
        )
        edit_group.roles.add(
            Role.objects.get(name="Translate"), Role.objects.get(name="Bulk editing")
        )
        edit_group.projects.add(editable_project)
        self.user.groups.add(view_group, edit_group)
        self.user.clear_permissions_cache()

        response = self.client.post(
            reverse("replace", kwargs={"path": workspace.get_url_path()}),
            {"q": "", "search": "Nazdar", "replacement": "Ahoj"},
        )

        self.assertContains(response, "Review and confirm the bulk edit changes.")
        self.assertEqual(
            [edit.unit for edit in response.context["matching"]], [editable_unit]
        )
        self.assertFalse(response.context["limited"])

    def test_replace_workspace_with_component_language_permission(self) -> None:
        workspace = Workspace.objects.create(name="Component access workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        self.user.groups.clear()
        group = Group.objects.create(name="Workspace component translator")
        group.roles.add(
            Role.objects.get(name="Translate"), Role.objects.get(name="Bulk editing")
        )
        group.components.add(self.component)
        group.languages.add(self.translation.language)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        self.assertFalse(self.user.has_perm("unit.edit", self.project))
        self.assertTrue(self.user.has_perm("unit.edit", self.unit))
        editable_scope = Unit.objects.filter_editable_scope(self.user)
        self.assertTrue(editable_scope.filter(pk=self.unit.pk).exists())
        self.assertFalse(
            editable_scope.filter(translation__component=self.component)
            .exclude(translation__language=self.translation.language)
            .exists()
        )

        response = self.client.get(workspace.get_absolute_url())

        self.assertContains(response, 'data-bs-target="#bulk-edit"')
        self.do_replace_test(
            reverse("replace", kwargs={"path": workspace.get_url_path()})
        )

    def test_replace_component(self) -> None:
        self.do_replace_test(reverse("replace", kwargs=self.kw_component))

    def test_replace_project_language(self) -> None:
        self.do_replace_test(
            reverse(
                "replace",
                kwargs={
                    "path": (self.project.slug, "-", self.translation.language.code)
                },
            )
        )

    def test_replace_plurals(self) -> None:
        unit = self.get_unit("Orangutan")
        url = reverse("replace", kwargs=self.kw_translation)
        self.edit_unit(
            "Orangutan",
            "Opice má %d banán.\n",
            target_1="Opice má %d banány.\n",
            target_2="Opice má %d banánů.\n",
        )
        response = self.client.post(
            url, {"q": "", "search": "Opice", "replacement": "Orangutan"}, follow=True
        )
        self.assertContains(response, "Review and confirm the bulk edit changes.")
        response = self.confirm_preview(response, url, [unit.pk])
        unit = self.get_unit("Orangutan")
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.assertEqual(
            unit.get_target_plurals(),
            [
                "Orangutan má %d banán.\n",
                "Orangutan má %d banány.\n",
                "Orangutan má %d banánů.\n",
            ],
        )


class BulkEditTest(ReusableViewTestCase):
    """Test for build edit functionality."""

    def setUp(self) -> None:
        super().setUp()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", fuzzy=True)
        self.unit = self.get_unit()
        self.make_manager()

    def test_preview_is_read_only_and_confirmation_applies(self) -> None:
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        before = (Change.objects.count(), PendingUnitChange.objects.count())
        response = self.client.post(
            url,
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_EMPTY,
                "preview": "1",
            },
        )
        self.assertContains(response, "Review and confirm")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.target, "Nazdar svete!\n")
        self.assertEqual(
            (Change.objects.count(), PendingUnitChange.objects.count()), before
        )
        response = self.client.post(
            url,
            {
                "bulk_confirmation": response.context["confirmation"],
                "preview_units": [self.unit.pk],
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.target, "")
        self.assertEqual(self.unit.state, STATE_EMPTY)
        change = self.unit.change_set.filter(action=ActionEvents.BULK_EDIT).latest("pk")
        self.assertEqual(change.user, self.user)
        self.assertTrue(
            PendingUnitChange.objects.filter(unit=self.unit, author=self.user).exists()
        )

    def test_preview_breadcrumbs_have_a_list_parent(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_EMPTY,
                "preview": "1",
            },
        )
        tree = html.fromstring(response.content)
        items = tree.xpath(
            "//li[contains(concat(' ', normalize-space(@class), ' '), ' breadcrumb-item ')]"
        )
        self.assertTrue(items)
        self.assertEqual(items[-1].text_content().strip(), "Bulk edit")
        self.assertTrue(all(item.getparent().tag == "ol" for item in items))

    def test_replacement_processes_each_selected_translation_once(self) -> None:
        other = self.create_po(
            project=self.project, slug="replace-peer", name="Replace peer"
        )
        outside = self.create_po(
            project=self.project, slug="replace-outside", name="Replace outside"
        )
        other_unit = other.translation_set.get(language_code="cs").unit_set.get(
            source=self.unit.source
        )
        outside_unit = outside.translation_set.get(language_code="cs").unit_set.get(
            source=self.unit.source
        )
        for unit in (self.unit, other_unit, outside_unit):
            unit.translate(self.user, "a", STATE_TRANSLATED, propagate=False)
        workspace = Workspace.objects.create(name="Bulk replacement")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        for scope in (self.project, workspace):
            for search_type in ("text", "regex"):
                with self.subTest(scope=type(scope).__name__, search_type=search_type):
                    Unit.objects.filter(
                        pk__in=[self.unit.pk, other_unit.pk, outside_unit.pk]
                    ).update(target="a\n")
                    url = reverse("bulk-edit", kwargs={"path": scope.get_url_path()})
                    response = self.client.post(
                        url,
                        {
                            "q": f"id:{self.unit.pk},{other_unit.pk}",
                            "state": -1,
                            "search_type": search_type,
                            "search": "a",
                            "replacement": "aa",
                            "preview": "1",
                        },
                    )
                    self.assertEqual(response.context["total"], 2)
                    self.assertEqual(
                        [edit.target for edit in response.context["matching"]],
                        [["aa\n"], ["aa\n"]],
                    )
                    response = self.client.post(
                        url,
                        {
                            "bulk_confirmation": response.context["confirmation"],
                            "apply_all": "1",
                        },
                        follow=True,
                    )
                    self.assertContains(
                        response, "Bulk edit completed, 2 strings were updated."
                    )
                    for unit in (self.unit, other_unit, outside_unit):
                        unit.refresh_from_db()
                        self.assertEqual(unit.target, "aa\n")

    def test_selected_translation_with_different_text_is_not_overwritten(self) -> None:
        other = self.create_po(
            project=self.project, slug="different-peer", name="Different peer"
        )
        other_unit = other.translation_set.get(language_code="cs").unit_set.get(
            source=self.unit.source
        )
        self.unit.translate(self.user, "a", STATE_TRANSLATED, propagate=False)
        other_unit.translate(self.user, "b", STATE_TRANSLATED, propagate=False)
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {
                "q": f"id:{self.unit.pk},{other_unit.pk}",
                "state": -1,
                "search": "a",
                "replacement": "aa",
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.unit.refresh_from_db()
        other_unit.refresh_from_db()
        self.assertEqual((self.unit.target, other_unit.target), ("aa\n", "b\n"))

    @override_settings(AUTOFIX_LIST=[])
    def test_regex_replacement_with_state_and_flags(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_TRANSLATED,
                "search_type": "regex",
                "search": r"(?P<greeting>Nazdar) (svete)",
                "replacement": r" \g<2> \g<greeting> ",
                "add_translation_flags": "max-length:100",
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.target, " svete Nazdar !\n")
        self.assertEqual(self.unit.state, STATE_TRANSLATED)
        self.assertIn("max-length:100", self.unit.extra_flags)

    def test_zero_width_replacement_fills_empty_translation(self) -> None:
        self.unit.translate(self.user, "", STATE_EMPTY)
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        response = self.client.post(
            url,
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_TRANSLATED,
                "preview": "1",
                "search_type": "regex",
                "search": "^",
                "replacement": "Prefix",
            },
        )
        self.assertEqual(response.context["matching"][0].state, STATE_TRANSLATED)
        self.client.post(
            url,
            {
                "bulk_confirmation": response.context["confirmation"],
                "preview_units": [self.unit.pk],
            },
        )
        self.unit.refresh_from_db()
        self.assertEqual(
            (self.unit.target, self.unit.state), ("Prefix\n", STATE_TRANSLATED)
        )

    def test_invalid_replacement_does_not_write(self) -> None:
        for search, replacement in [("(", "x"), ("(x)", r"\g<missing>")]:
            with self.subTest(search=search):
                form = BulkEditForm(
                    self.user,
                    self.translation,
                    data={
                        "q": "state:translated",
                        "state": -1,
                        "search_type": "regex",
                        "search": search,
                        "replacement": replacement,
                    },
                )
                self.assertFalse(form.is_valid())
                self.assertIn(
                    "Invalid regular expression or replacement", str(form.errors)
                )

    def test_clearing_sources_is_excluded(self) -> None:
        source = self.unit.source_unit
        old = source.target
        self.client.post(
            reverse("bulk-edit", kwargs=self.kw_component),
            {
                "q": f"id:{source.pk}",
                "state": STATE_EMPTY,
            },
        )
        source.refresh_from_db()
        self.assertEqual(source.target, old)

    def test_editable_source_replacement_cannot_clear(self) -> None:
        component = self.create_json_mono(
            project=self.project, slug="bulk-source", name="Bulk source"
        )
        source = component.source_translation.unit_set.get(source__startswith="Hello")
        self.assertTrue(self.user.has_perm("unit.edit", source))
        url = reverse("bulk-edit", kwargs={"path": component.get_url_path()})
        original = source.target
        response = self.client.post(
            url,
            {
                "q": f"id:{source.pk}",
                "state": -1,
                "search": original,
                "replacement": "",
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, no strings were updated.")
        source.refresh_from_db()
        self.assertEqual(source.target, original)
        response = self.client.post(
            url,
            {
                "q": f"id:{source.pk}",
                "state": -1,
                "search": "Hello",
                "replacement": "Hi",
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        source.refresh_from_db()
        self.assertEqual(source.target, original.replace("Hello", "Hi"))

    def test_empty_replacement_clears_state(self) -> None:
        self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "q": f"id:{self.unit.pk}",
                "state": -1,
                "search": "Nazdar svete!\n",
                "replacement": "",
            },
        )
        self.unit.refresh_from_db()
        self.assertEqual((self.unit.target, self.unit.state), ("", STATE_EMPTY))

    def test_replacement_does_not_narrow_other_operations(self) -> None:
        self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_TRANSLATED,
                "search": "absent text",
                "replacement": "x",
            },
        )
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.target, "Nazdar svete!\n")
        self.assertEqual(self.unit.state, STATE_TRANSLATED)

    def test_confirmation_rejects_unshown_units(self) -> None:
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        response = self.client.post(
            url,
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_EMPTY,
                "preview": "1",
            },
        )
        response = self.client.post(
            url,
            {
                "bulk_confirmation": response.context["confirmation"],
                "preview_units": [self.unit.source_unit_id],
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_confirmation_rechecks_permissions(self) -> None:
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        response = self.client.post(
            url,
            {
                "q": f"id:{self.unit.pk}",
                "state": STATE_EMPTY,
                "preview": "1",
            },
        )
        self.user.groups.clear()
        self.user.clear_permissions_cache()
        response = self.client.post(
            url,
            {
                "bulk_confirmation": response.context["confirmation"],
                "apply_all": "1",
            },
        )
        self.assertIn(response.status_code, (403, 404))
        self.unit.refresh_from_db()
        self.assertNotEqual(self.unit.target, "")

    def test_preview_limit_and_apply_all(self) -> None:
        units = Unit.objects.bulk_create(
            [
                Unit(
                    translation=self.translation,
                    source=f"Bulk {index}",
                    target=f"Target {index}",
                    id_hash=-90_000_000 - index,
                    source_unit=self.unit.source_unit,
                    state=STATE_FUZZY,
                    original_state=STATE_FUZZY,
                    position=20_000 + index,
                )
                for index in range(251)
            ]
        )
        ids = [unit.pk for unit in units]
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        response = self.client.post(
            url,
            {
                "q": "id:" + ",".join(map(str, ids)),
                "state": STATE_TRANSLATED,
                "preview": "1",
            },
        )
        self.assertEqual(response.context["total"], 251)
        self.assertEqual(len(response.context["matching"]), 250)
        self.assertTrue(response.context["limited"])
        token = response.context["confirmation"]
        displayed = [edit.unit.pk for edit in response.context["matching"]]
        self.client.post(url, {"bulk_confirmation": token, "preview_units": displayed})
        self.assertEqual(
            Unit.objects.filter(pk__in=ids, state=STATE_TRANSLATED).count(), 250
        )
        Unit.objects.filter(pk__in=ids).update(state=STATE_FUZZY)
        self.client.post(url, {"bulk_confirmation": token, "apply_all": "1"})
        self.assertEqual(
            Unit.objects.filter(pk__in=ids, state=STATE_TRANSLATED).count(), 251
        )

    def test_regex_output_failure_does_not_write(self) -> None:
        self.unit.translate(self.user, "a" * 8000, STATE_TRANSLATED)
        before = (Change.objects.count(), PendingUnitChange.objects.count())
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        for preview in ("1", ""):
            with self.subTest(preview=preview):
                response = self.client.post(
                    url,
                    {
                        "q": f"id:{self.unit.pk}",
                        "state": -1,
                        "preview": preview,
                        "search_type": "regex",
                        "search": r"(?=(.*))",
                        "replacement": r"\1",
                        "add_flags": "max-length:100",
                    },
                    follow=True,
                )
                self.assertContains(response, "output exceeds")
                self.assertEqual(
                    (Change.objects.count(), PendingUnitChange.objects.count()), before
                )
                self.unit.refresh_from_db()
                self.assertEqual(self.unit.target, "a" * 8000 + "\n")
                self.unit.source_unit.refresh_from_db()
                self.assertNotIn("max-length:100", self.unit.source_unit.extra_flags)

    def test_regex_budget_shared_across_components(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(
            allow_translation_propagation=False
        )
        other = self.create_po(
            project=self.project,
            slug="regex-other",
            name="Regex other",
            allow_translation_propagation=False,
        )
        other_unit = other.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        for unit in (self.unit, other_unit):
            unit.translate(self.user, "value", STATE_TRANSLATED)
        with patch("weblate.utils.bulk_regex.OUTPUT_LIMIT", 7):
            response = self.client.post(
                reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
                {
                    "q": f"id:{self.unit.pk},{other_unit.pk}",
                    "state": -1,
                    "search_type": "regex",
                    "search": "^value",
                    "replacement": "values",
                },
                follow=True,
            )
        self.assertContains(response, "output exceeds")
        self.unit.refresh_from_db()
        other_unit.refresh_from_db()
        self.assertEqual(
            sorted([self.unit.target, other_unit.target]), ["value\n", "values\n"]
        )

    def test_regex_timeout_rolls_back_component(self) -> None:
        url = reverse("bulk-edit", kwargs=self.kw_translation)
        with patch(
            "weblate.trans.bulk.BulkReplacement.replace",
            side_effect=ValidationError("Timed out"),
        ):
            response = self.client.post(
                url,
                {
                    "q": f"id:{self.unit.pk}",
                    "state": STATE_TRANSLATED,
                    "search_type": "regex",
                    "search": "Nazdar",
                    "replacement": "Hello",
                    "add_flags": "max-length:100",
                },
                follow=True,
            )
        self.assertContains(response, "Bulk edit failed: Timed out")
        self.unit.refresh_from_db()
        self.unit.source_unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_FUZZY)
        self.assertNotIn("max-length:100", self.unit.source_unit.extra_flags)

    def do_bulk_edit_test(self, url) -> None:
        response = self.client.post(
            url, {"q": "state:needs-editing", "state": STATE_TRANSLATED}, follow=True
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.assertEqual(self.get_unit().state, STATE_TRANSLATED)

    def test_related_filter_updates_unit_once(self) -> None:
        Comment.objects.bulk_create(
            [Comment(unit=self.unit, user=self.user, comment="alpha") for _ in range(3)]
        )
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {
                "q": f"id:{self.unit.pk} AND comment:alpha",
                "state": STATE_TRANSLATED,
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_TRANSLATED)
        self.assertEqual(
            self.unit.change_set.filter(action=ActionEvents.BULK_EDIT).count(), 1
        )

    def test_no_match(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:approved", "state": STATE_FUZZY},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, no strings were updated.")
        unit = self.get_unit()
        self.assertEqual(unit.state, STATE_FUZZY)

    def test_bulk_edit(self) -> None:
        self.do_bulk_edit_test(reverse("bulk-edit", kwargs=self.kw_translation))

    def test_bulk_edit_project(self) -> None:
        self.do_bulk_edit_test(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()})
        )

    def test_bulk_edit_component(self) -> None:
        self.do_bulk_edit_test(reverse("bulk-edit", kwargs=self.kw_component))

    def test_bulk_edit_project_language(self) -> None:
        self.do_bulk_edit_test(
            reverse(
                "bulk-edit",
                kwargs={
                    "path": (self.project.slug, "-", self.translation.language.code)
                },
            )
        )

    def test_bulk_edit_selected_units(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"units": [self.unit.pk], "state": STATE_TRANSLATED},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.assertEqual(self.get_unit().state, STATE_TRANSLATED)

    def test_bulk_edit_selected_units_multiple(self) -> None:
        other = self.get_unit("Thank you for using Weblate.")
        other.state = STATE_FUZZY
        other.save(update_fields=["state"])

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"units": [self.unit.pk, other.pk], "state": STATE_TRANSLATED},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 2 strings were updated.")
        self.assertEqual(self.get_unit().state, STATE_TRANSLATED)
        other.refresh_from_db()
        self.assertEqual(other.state, STATE_TRANSLATED)

    def test_bulk_edit_selected_units_single_field(self) -> None:
        """
        Selection is posted as one comma separated field.

        One field per string would exceed DATA_UPLOAD_MAX_NUMBER_FIELDS on a
        full page, as the maximal page size matches it.
        """
        other = self.get_unit("Thank you for using Weblate.")
        other.state = STATE_FUZZY
        other.save(update_fields=["state"])

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "units": f"{self.unit.pk},{other.pk}",
                "state": STATE_TRANSLATED,
            },
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 2 strings were updated.")
        self.assertEqual(self.get_unit().state, STATE_TRANSLATED)
        other.refresh_from_db()
        self.assertEqual(other.state, STATE_TRANSLATED)

    def test_bulk_edit_selected_units_outside_scope(self) -> None:
        other = self.get_unit(language="de")
        other.state = STATE_FUZZY
        other.save(update_fields=["state"])

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"units": [other.pk], "state": STATE_TRANSLATED},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, no strings were updated.")
        other.refresh_from_db()
        self.assertEqual(other.state, STATE_FUZZY)

    def test_bulk_edit_selected_units_invalid(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"units": ["invalid"], "state": STATE_TRANSLATED},
            follow=True,
        )
        self.assertContains(response, "Could not process form!")
        self.assertEqual(self.get_unit().state, STATE_FUZZY)

    def test_bulk_edit_requires_query_or_units(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"state": STATE_TRANSLATED},
            follow=True,
        )
        self.assertContains(response, "Could not process form!")
        self.assertContains(response, "Select strings to edit or enter a search query.")
        self.assertEqual(self.get_unit().state, STATE_FUZZY)

    def test_bulk_edit_next_redirect(self) -> None:
        search_url = reverse("search", kwargs=self.kw_translation)
        next_url = f"{search_url}?q=state%3Aneeds-editing&page=1"
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"units": [self.unit.pk], "state": STATE_TRANSLATED, "next": next_url},
        )
        self.assertRedirects(response, next_url)
        self.assertEqual(self.get_unit().state, STATE_TRANSLATED)

    def test_bulk_edit_next_redirect_invalid(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "units": [self.unit.pk],
                "state": STATE_TRANSLATED,
                "next": "https://example.net/evil",
            },
        )
        self.assertRedirects(response, self.translation.get_absolute_url())
        self.assertEqual(self.get_unit().state, STATE_TRANSLATED)

    def test_bulk_edit_fuzzy_alias_includes_substates(self) -> None:
        self.unit.state = STATE_NEEDS_REWRITING
        self.unit.save(update_fields=["state"])

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"q": "is:needs-editing", "state": STATE_TRANSLATED},
            follow=True,
        )

        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_TRANSLATED)

    def test_bulk_edit_or_query_includes_substates(self) -> None:
        self.unit.state = STATE_NEEDS_CHECKING
        self.unit.save(update_fields=["state"])

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {
                "q": "state:needs-checking OR state:needs-rewriting",
                "state": STATE_TRANSLATED,
            },
            follow=True,
        )

        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_TRANSLATED)

    def test_bulk_edit_requires_bulk_permission_per_unit(self) -> None:
        limited_user = User.objects.create_user(
            "limited-bulk", "limited-bulk@example.com", "limited-bulk"
        )
        group = Group.objects.create(
            name="Limited bulk", language_selection=SELECTION_ALL
        )
        group.roles.add(Role.objects.get(name="Translate"))
        group.components.add(self.component)
        limited_user.groups.add(group)
        limited_user.clear_permissions_cache()

        self.assertTrue(limited_user.has_perm("unit.edit", self.unit))
        self.assertFalse(limited_user.has_perm("unit.bulk_edit", self.unit))

        updated = bulk_perform(
            limited_user,
            Unit.objects.filter(translation__component=self.component),
            query="state:needs-editing",
            target_state=STATE_TRANSLATED,
            add_flags="",
            remove_flags="",
            add_labels=self.project.label_set.none(),
            remove_labels=self.project.label_set.none(),
            project=self.project,
            components=[self.component],
        )

        self.assertEqual(updated, 0)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_FUZZY)

    def test_bulk_edit_skips_restricted_language(self) -> None:
        limited_user = User.objects.create_user(
            "restricted-bulk", "restricted-bulk@example.com", "restricted-bulk"
        )
        group = Group.objects.create(
            name="Restricted bulk", language_selection=SELECTION_ALL
        )
        group.roles.add(
            Role.objects.get(name="Translate"), Role.objects.get(name="Bulk editing")
        )
        group.components.add(self.component)
        limited_user.groups.add(group)
        limited_user.clear_permissions_cache()
        self.assertTrue(limited_user.has_perm("unit.edit", self.unit))
        self.assertTrue(limited_user.has_perm("unit.bulk_edit", self.unit))

        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            restrict_direct_editing=True,
        )
        unit = Unit.objects.get(pk=self.unit.pk)

        updated = bulk_perform(
            limited_user,
            Unit.objects.filter(pk=unit.pk),
            query="state:needs-editing",
            target_state=STATE_TRANSLATED,
            add_flags="",
            remove_flags="",
            add_labels=self.project.label_set.none(),
            remove_labels=self.project.label_set.none(),
            project=self.project,
            components=[self.component],
        )

        self.assertEqual(updated, 0)
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_FUZZY)

    def test_bulk_edit_requires_review_permission_to_approve(self) -> None:
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        limited_user = User.objects.create_user(
            "limited-approve", "limited-approve@example.com", "limited-approve"
        )
        group = Group.objects.create(
            name="Limited approve", language_selection=SELECTION_ALL
        )
        group.roles.add(
            Role.objects.get(name="Translate"), Role.objects.get(name="Bulk editing")
        )
        group.components.add(self.component)
        limited_user.groups.add(group)
        limited_user.clear_permissions_cache()

        self.assertTrue(limited_user.has_perm("unit.edit", self.unit))
        self.assertTrue(limited_user.has_perm("unit.bulk_edit", self.unit))
        self.assertFalse(limited_user.has_perm("unit.review", self.unit))

        updated = bulk_perform(
            limited_user,
            Unit.objects.filter(translation__component=self.component),
            query="state:needs-editing",
            target_state=STATE_APPROVED,
            add_flags="",
            remove_flags="",
            add_labels=self.project.label_set.none(),
            remove_labels=self.project.label_set.none(),
            project=self.project,
            components=[self.component],
        )

        self.assertEqual(updated, 0)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_FUZZY)

    def test_bulk_flags(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:needs-editing", "state": -1, "add_flags": "python-format"},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        unit = self.get_unit()
        self.assertIn("python-format", unit.all_flags)
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:needs-editing", "state": -1, "remove_flags": "python-format"},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        unit = self.get_unit()
        self.assertNotIn("python-format", unit.all_flags)

    def test_bulk_read_only(self) -> None:
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "language:en", "state": -1, "add_flags": "read-only"},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 4 strings were updated.")
        unit = self.get_unit()
        self.assertIn("read-only", unit.all_flags)
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "language:en", "state": -1, "remove_flags": "read-only"},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 4 strings were updated.")
        unit = self.get_unit()
        self.assertNotIn("read-only", unit.all_flags)

    def test_bulk_labels(self) -> None:
        label = self.project.label_set.create(name="Test label", color="black")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
                {"q": "state:needs-editing", "state": -1, "add_labels": label.pk},
                follow=True,
            )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:needs-editing", "state": -1, "add_labels": label.pk},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, no strings were updated.")
        unit = self.get_unit()
        self.assertIn(label, unit.all_labels)
        self.assertEqual(getattr(unit.translation.stats, f"label:{label.name}"), 1)
        # Clear local outdated cache
        unit.source_unit.translation.stats.clear()
        self.assertEqual(
            getattr(unit.source_unit.translation.stats, f"label:{label.name}"),
            1,
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
                {"q": "state:needs-editing", "state": -1, "remove_labels": label.pk},
                follow=True,
            )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:needs-editing", "state": -1, "remove_labels": label.pk},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, no strings were updated.")
        unit = self.get_unit()
        self.assertNotIn(label, unit.labels.all())
        self.assertEqual(getattr(unit.translation.stats, f"label:{label.name}"), 0)
        # Clear local outdated cache
        unit.source_unit.translation.stats.clear()
        self.assertEqual(
            getattr(unit.source_unit.translation.stats, f"label:{label.name}"),
            0,
        )

    def test_bulk_translation_label(self) -> None:
        label = self.project.label_set.create(name="Test label", color="black")
        unit = self.get_unit()
        unit.source_unit.labels.add(label)
        # Clear local outdated cache
        unit.translation.stats.clear()
        self.assertEqual(
            getattr(unit.translation.stats, f"label:{label.name}"),
            1,
        )
        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:>=empty", "state": -1, "remove_labels": label.pk},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")
        unit = self.get_unit()
        self.assertNotIn(label, unit.source_unit.labels.all())
        # Clear local outdated cache
        unit.translation.stats.clear()
        self.assertEqual(
            getattr(unit.translation.stats, f"label:{label.name}"),
            0,
        )

    def test_source_state(self) -> None:
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            mono = Component.objects.create(
                name="Test2",
                slug="test2",
                project=self.project,
                repo="weblate://test/test",
                file_format="json",
                filemask="json-mono/*.json",
                template="json-mono/en.json",
            )
        # Translate single unit
        translation = mono.translation_set.get(language_code="cs")
        translation.unit_set.get(context="hello").translate(
            self.user, "Ahoj světe", STATE_TRANSLATED
        )
        self.assertEqual(translation.unit_set.filter(state=STATE_READONLY).count(), 0)
        self.assertEqual(translation.unit_set.filter(state=STATE_TRANSLATED).count(), 1)

        url = reverse("bulk-edit", kwargs={"path": mono.get_url_path()})

        # Mark all source strings as needing edit and that should turn all
        # translated strings read-only
        response = self.client.post(
            url, {"q": "language:en", "state": STATE_FUZZY}, follow=True
        )
        self.assertContains(response, "Bulk edit completed, 4 strings were updated.")
        self.assertEqual(translation.unit_set.filter(state=STATE_READONLY).count(), 0)
        self.assertEqual(translation.unit_set.filter(state=STATE_TRANSLATED).count(), 1)

        # Mark all source strings as needing edit and that should turn all
        # translated strings back to translated
        response = self.client.post(
            url, {"q": "language:en", "state": STATE_TRANSLATED}, follow=True
        )
        self.assertContains(response, "Bulk edit completed, 4 strings were updated.")
        self.assertEqual(translation.unit_set.filter(state=STATE_READONLY).count(), 0)
        self.assertEqual(translation.unit_set.filter(state=STATE_TRANSLATED).count(), 1)

    def test_bulk_approve_clears_automatically_translated(self) -> None:
        self.project.translation_review = True
        self.project.save()

        unit = self.get_unit()
        unit.automatically_translated = True
        unit.save()
        self.assertTrue(self.get_unit().automatically_translated)

        response = self.client.post(
            reverse("bulk-edit", kwargs={"path": self.project.get_url_path()}),
            {"q": "state:<translated", "state": STATE_APPROVED},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")

        unit = self.get_unit()
        self.assertEqual(unit.state, STATE_APPROVED)
        self.assertFalse(unit.automatically_translated)

    def test_bulk_edit_creates_change_and_pending_unit_change(self) -> None:
        """Bulk edit creates Change and PendingUnitChange records via bulk insert."""
        PendingUnitChange.objects.filter(unit=self.unit).delete()
        initial_change_count = Change.objects.filter(
            action=ActionEvents.BULK_EDIT
        ).count()

        response = self.client.post(
            reverse("bulk-edit", kwargs=self.kw_translation),
            {"q": "state:needs-editing", "state": STATE_TRANSLATED},
            follow=True,
        )
        self.assertContains(response, "Bulk edit completed, 1 string was updated.")

        self.assertEqual(
            Change.objects.filter(action=ActionEvents.BULK_EDIT).count(),
            initial_change_count + 1,
        )
        self.assertTrue(PendingUnitChange.objects.filter(unit=self.unit).exists())
