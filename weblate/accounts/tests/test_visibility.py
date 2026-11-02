# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from weblate.accounts.visibility import is_resource_bounded
from weblate.utils.search import SearchQueryError, parse_query


class VisibilityQueryTest(SimpleTestCase):
    def test_boolean_scopes(self) -> None:
        user = SimpleNamespace(
            allowed_projects=[], needs_component_restrictions_filter=False
        )
        for query, expected in (
            ("", False),
            ("alice", False),
            ("language:cs", False),
            ("contributes:project", True),
            ("NOT contributes:project", False),
            ("contributes:project OR alice", False),
            ("alice OR contributes:project", False),
            ("contributes:project AND alice", True),
            ("alice contributes:project", True),
            ("contributes:project OR contributes:other", True),
            ("contributes:project AND (alice OR bob)", True),
            ("(contributes:project AND alice) OR bob", False),
            ("(contributes:project OR alice) AND language:cs", False),
            ("NOT (NOT contributes:project)", True),
            ("NOT (contributes:project OR alice)", False),
        ):
            with self.subTest(query=query):
                filters, _ = parse_query(query, parser="user", user=user)
                self.assertEqual(is_resource_bounded(filters), expected)

    def test_nonconcrete_scope(self) -> None:
        for query in ("contributes:*", 'contributes:""', "contributes:/test/"):
            with self.subTest(query=query), self.assertRaises(SearchQueryError):
                parse_query(
                    query, parser="user", user=SimpleNamespace(allowed_projects=[])
                )
