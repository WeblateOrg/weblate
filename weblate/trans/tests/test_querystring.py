# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression tests for query strings in navigation templates."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from django.core.paginator import Paginator
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse
from lxml import html

from weblate.trans.models import Project
from weblate.trans.templatetags.translations import format_last_changes_content
from weblate.trans.tests.test_views import ViewTestCase


class SortedPaginator(Paginator):
    sort_by = "-name"


class PaginatorQueryTest(SimpleTestCase):
    def render_paginator(self, query: str, **context: object) -> html.HtmlElement:
        request = RequestFactory().get(f"/?{query}")
        paginator = SortedPaginator(range(60), 20)
        return html.fromstring(
            render_to_string(
                "paginator.html",
                {
                    "page_obj": paginator.page(2),
                    "anchor": "results",
                    "request": request,
                    **context,
                },
            )
        )

    def test_links_and_jump_form_preserve_repeated_filters(self) -> None:
        params = QueryDict(mutable=True)
        params.setlist("type", ["all", "todo"])
        params.update({"q": 'Žluťoučký & "<text>"', "page": "99", "limit": "500"})
        params.setlist("sort_by", ["name", "translated"])
        document = self.render_paginator(params.urlencode())
        links = document.xpath('//a[contains(@class, "page-link")][@href!="#"]')
        self.assertEqual(len(links), 4)
        for link, page in zip(links, (1, 1, 3, 3), strict=True):
            with self.subTest(page=page):
                url = urlsplit(link.get("href"))
                self.assertEqual(url.fragment, "results")
                self.assertEqual(
                    parse_qs(url.query),
                    {
                        "q": [params["q"]],
                        "type": ["all", "todo"],
                        "page": [str(page)],
                        "limit": ["20"],
                        "sort_by": ["-name"],
                    },
                )
        form = document.xpath("//form")[0]
        self.assertEqual(form.get("action"), "#results")
        fields = list(form.form_values())
        self.assertEqual(fields.count(("type", "all")), 1)
        self.assertEqual(fields.count(("type", "todo")), 1)
        self.assertEqual([value for key, value in fields if key == "page"], ["2"])
        self.assertEqual([value for key, value in fields if key == "limit"], ["20"])
        self.assertEqual(
            [value for key, value in fields if key == "sort_by"], ["-name"]
        )
        self.assertIn(("q", params["q"]), fields)

    def test_empty_validated_filters_do_not_fall_back_to_request(self) -> None:
        document = self.render_paginator(
            "q=invalid&checksum=stale", query_params=QueryDict()
        )
        for link in document.xpath('//a[@href!="#"]/@href'):
            self.assertNotIn("q", parse_qs(urlsplit(link).query))
            self.assertNotIn("checksum", parse_qs(urlsplit(link).query))
        self.assertFalse(document.xpath('//input[@name="q" or @name="checksum"]'))

    def test_filter_names_do_not_shadow_dictionary_methods(self) -> None:
        document = self.render_paginator("lists=all&lists=todo&items=value")
        fields = list(document.xpath("//form")[0].form_values())
        self.assertIn(("lists", "all"), fields)
        self.assertIn(("lists", "todo"), fields)
        self.assertIn(("items", "value"), fields)

    def test_external_form_and_validated_filters(self) -> None:
        params = QueryDict("type=all&type=todo")
        document = self.render_paginator(
            "q=ignored", query_params=params, paginator_form="paginator-form"
        )
        self.assertFalse(document.xpath("//form"))
        fields = document.xpath("//input")
        self.assertTrue(fields)
        self.assertTrue(all(field.get("form") == "paginator-form" for field in fields))
        self.assertEqual(params, QueryDict("type=all&type=todo"))


class NavigationQueryTest(ViewTestCase):
    def test_editor_links_use_validated_search_and_destination_position(self) -> None:
        self.create_link_existing()
        unit = self.get_unit("Thank you for using Weblate.")
        response = self.client.get(
            self.translation.get_translate_url(),
            {
                "q": "source:Weblate",
                "checksum": unit.checksum,
                "offset": 99,
                "unrelated": "drop",
            },
        )
        self.assertEqual(response.status_code, 200)
        document = html.fromstring(response.content)
        zen_path = reverse("zen", kwargs={"path": self.translation.get_url_path()})
        zen_url = next(
            url for url in document.xpath("//a/@href") if urlsplit(url).path == zen_path
        )
        self.assertEqual(
            parse_qs(urlsplit(zen_url).query),
            {"q": ["source:Weblate"], "offset": [str(response.context["offset"])]},
        )
        actions = document.xpath('//form[contains(@action, "unit_id=")]/@action')
        self.assertEqual(len(actions), 1)
        self.assertEqual(
            parse_qs(urlsplit(actions[0]).query),
            {
                "q": ["source:Weblate"],
                "offset": [str(response.context["offset"])],
                "checksum": [unit.checksum],
                "unit_id": [str(unit.pk)],
            },
        )
        self.assertEqual(response.context["search_form"].data["offset"], "1")
        self.assertEqual(response.context["search_form"].data["checksum"], "")
        response = self.client.get(zen_url)
        self.assertEqual(response.status_code, 200)
        document = html.fromstring(response.content)
        editor_url = next(
            url
            for url in document.xpath("//a/@href")
            if urlsplit(url).path == self.translation.get_translate_url()
        )
        self.assertEqual(
            parse_qs(urlsplit(editor_url).query), {"q": ["source:Weblate"]}
        )

    def test_embedded_links_replace_request_checksum(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        response = self.client.get(
            reverse("search", kwargs={"path": self.translation.get_url_path()}),
            {
                "q": "source:Weblate",
                "checksum": unit.checksum,
                "offset": 99,
                "unrelated": "drop",
            },
        )
        self.assertEqual(response.status_code, 200)
        document = html.fromstring(response.content)
        links = document.xpath('//a[contains(@href, "checksum=")]/@href')
        self.assertTrue(links)
        checksums = set()
        for link in links:
            params = parse_qs(urlsplit(link).query)
            self.assertEqual(set(params), {"q", "checksum"})
            self.assertEqual(params["q"], ["source:Weblate"])
            self.assertEqual(len(params["checksum"]), 1)
            checksums.add(params["checksum"][0])
        self.assertEqual(
            checksums,
            {
                unit.checksum
                for unit in self.translation.unit_set.filter(source__contains="Weblate")
            },
        )

    def test_embedded_links_with_fallback_sorting(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        unit.context = "String context"
        for include_search, params in (
            (False, QueryDict("q=ignored")),
            (True, QueryDict()),
        ):
            for sort_query in (None, "-source"):
                with self.subTest(include_search=include_search, sort_query=sort_query):
                    document = html.fromstring(
                        render_to_string(
                            "snippets/embed-units.html",
                            {
                                "units": [unit],
                                "translation": self.translation,
                                "include_search": include_search,
                                "query_params": params,
                                "sort_query": sort_query,
                                "search_query": "",
                                "force_source": True,
                                "request": RequestFactory().get(
                                    "/?q=unrelated&checksum=stale"
                                ),
                            },
                        )
                    )
                    links = document.xpath(
                        '//tbody//a[contains(@href, "checksum=")]/@href'
                    )
                    self.assertEqual(len(links), 3)
                    expected = {"checksum": [unit.checksum]}
                    if sort_query:
                        expected["sort_by"] = [sort_query]
                    for link in links:
                        self.assertEqual(
                            urlsplit(link).path, self.translation.get_translate_url()
                        )
                        self.assertEqual(parse_qs(urlsplit(link).query), expected)

    def test_revert_links_without_request_context(self) -> None:
        unit = self.change_unit("Changed target", user=self.user)
        change = unit.change_set.latest("timestamp")
        for search_url, expected in (
            (None, {}),
            ("q=source%3AWeblate", {"q": ["source:Weblate"], "offset": ["2"]}),
        ):
            with self.subTest(search_url=search_url):
                document = html.fromstring(
                    render_to_string(
                        "snippets/last-changes-content.html",
                        format_last_changes_content(
                            [change], self.user, search_url=search_url, offset=2
                        ),
                    )
                )
                links = document.xpath('//a[contains(@href, "revert=")]/@href')
                self.assertEqual(len(links), 1)
                self.assertEqual(
                    parse_qs(urlsplit(links[0]).query),
                    {
                        **expected,
                        "checksum": [unit.checksum],
                        "revert": [str(change.pk)],
                    },
                )

    def test_project_sort_links(self) -> None:
        for index in range(10):
            Project.objects.create(name=f"Project {index}", slug=f"project-{index}")
        for current, expected in (
            ("name", "-name"),
            ("-name", "name"),
            ("translated", "name"),
        ):
            with self.subTest(current=current):
                response = self.client.get(
                    reverse("projects"),
                    {"sort_by": current, "limit": "10", "page": "2"},
                )
                self.assertEqual(response.status_code, 200)
                document = html.fromstring(response.content)
                links = document.xpath('//th//a[contains(@href, "sort_by=")]/@href')
                self.assertTrue(links)
                self.assertEqual(
                    parse_qs(urlsplit(links[0]).query),
                    {"page": ["2"], "limit": ["10"], "sort_by": [expected]},
                )
                for link in links:
                    self.assertEqual(len(parse_qs(urlsplit(link).query)["sort_by"]), 1)

    @override_settings(DEBUG=True, INTERNAL_IPS=["127.0.0.1"])
    def test_history_links_keep_only_validated_filters(self) -> None:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        response = self.client.get(
            reverse("changes"),
            {
                "user": self.user.username,
                "page": "1",
                "limit": "25",
                "unrelated": "drop",
            },
        )
        self.assertEqual(response.status_code, 200)
        document = html.fromstring(response.content)
        destinations = {
            reverse("changes"),
            reverse("changes-csv"),
            reverse("changes-rss"),
        }
        links = [
            url
            for url in document.xpath("//a/@href")
            if urlsplit(url).path in destinations
        ]
        self.assertTrue(links)
        self.assertEqual({urlsplit(url).path for url in links}, destinations)
        self.assertTrue(any("digest=1" in url for url in links))
        for link in links:
            params = parse_qs(urlsplit(link).query)
            # The Changes entry in the global navigation has no filters.
            if not params:
                continue
            expected = {"user": [self.user.username]}
            if "digest" in params:
                expected["digest"] = ["1"]
            self.assertEqual(params, expected)
