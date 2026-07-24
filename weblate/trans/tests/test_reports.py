# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from weblate.auth.models import User
from weblate.memory.models import Memory
from weblate.trans.forms import (
    MIN_COST_ESTIMATE_TM_THRESHOLD,
    CountsReportsForm,
    get_report_language_choices,
)
from weblate.trans.models import (
    Category,
    Change,
    PendingUnitChange,
    Project,
    Report,
    Suggestion,
    Unit,
)
from weblate.trans.models.component import ComponentLink
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import TESTPASSWORD
from weblate.trans.views.reports import (
    generate_cost_estimate,
    generate_counts,
    generate_credits,
)
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY

COUNTS_DATA = [
    {
        "count": 1,
        "count_edit": 0,
        "count_new": 1,
        "name": "Weblate <b>Test</b>",
        "words": 2,
        "words_edit": 0,
        "words_new": 2,
        "chars": 14,
        "chars_edit": 0,
        "chars_new": 14,
        "email": "weblate@example.org",
        "t_chars": 14,
        "t_chars_edit": 0,
        "t_chars_new": 14,
        "t_words": 2,
        "t_words_edit": 0,
        "t_words_new": 2,
        "count_approve": 0,
        "words_approve": 0,
        "chars_approve": 0,
        "t_chars_approve": 0,
        "t_words_approve": 0,
        "edits": 14,
        "edits_approve": 0,
        "edits_edit": 0,
        "edits_new": 14,
    }
]


class BaseReportsTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.full_name = "Weblate <b>Test</b>"
        self.user.save()
        self.counts_data = [
            {**COUNTS_DATA[0], "date_joined": self.user.date_joined.isoformat()}
        ]
        self.maxDiff = None

    def add_change(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

    def generate_count_data(
        self, counting_mode: str = CountsReportsForm.COUNTING_MODE_UNIQUE
    ):
        now = timezone.now()
        return generate_counts(
            None,
            now - timedelta(days=1),
            now + timedelta(days=1),
            "",
            "date_joined",
            "ascending",
            counting_mode,
            component=self.component,
        )

    def get_cost_rates(self):
        return {
            "rate_new": Decimal(100),
            "rate_needs_editing": Decimal(50),
            "rate_tm_100": Decimal(0),
            "rate_tm_fuzzy": Decimal(50),
            "rate_repetition": Decimal(0),
        }

    def generate_cost_data(
        self,
        *,
        q: str = "state:<translated",
        threshold: int = 80,
        entity=None,
    ):
        return generate_cost_estimate(
            self.user,
            "",
            q,
            Decimal("0.10"),
            threshold,
            self.get_cost_rates(),
            self.component if entity is None else entity,
        )

    def add_memory(self, source: str) -> None:
        Memory.objects.create(
            source_language=self.component.source_language,
            target_language=self.translation.language,
            source=source,
            target="Translation memory result",
            origin="test",
            legacy_project=self.project,
            status=Memory.STATUS_ACTIVE,
        )

    def move_component_to_child_category(self) -> Category:
        parent = self.create_category(project=self.project)
        child = self.create_category(project=self.project, category=parent)
        self.component.category = child
        self.component.save(update_fields=["category"])
        return parent


class ReportsTest(BaseReportsTest):
    def test_credits_empty(self) -> None:
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            self.component,
            "count",
            "ascending",
        )
        self.assertEqual(data, [])

    def test_credits_one(self, expected_count=1) -> None:
        self.add_change()
        expected = [
            {
                "Czech": [
                    {
                        "email": "weblate@example.org",
                        "full_name": "Weblate <b>Test</b>",
                        "username": "testuser",
                        "change_count": expected_count,
                        "date_joined": self.user.date_joined.isoformat(),
                    }
                ]
            }
        ]
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            self.component,
            "date_joined",
            "ascending",
        )
        self.assertEqual(data, expected)
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "cs",
            self.component,
            "date_joined",
            "ascending",
        )
        self.assertEqual(data, expected)
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "de",
            self.component,
            "date_joined",
            "ascending",
        )
        self.assertEqual(data, [])

    def test_credits_more(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete2!\n")
        self.test_credits_one(expected_count=2)

    def test_credits_include_child_category_components(self) -> None:
        parent = self.move_component_to_child_category()
        self.add_change()

        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "cs",
            parent,
            "date_joined",
            "ascending",
        )

        self.assertEqual(
            data,
            [
                {
                    "Czech": [
                        {
                            "email": "weblate@example.org",
                            "full_name": "Weblate <b>Test</b>",
                            "username": "testuser",
                            "change_count": 1,
                            "date_joined": self.user.date_joined.isoformat(),
                        }
                    ]
                }
            ],
        )

    def test_category_reports_exclude_linked_components(self) -> None:
        project = Project.objects.create(
            name="Linked report project",
            slug="linked-report-project",
        )
        category = self.create_category(project=project)
        ComponentLink.objects.create(
            component=self.component,
            project=project,
            category=category,
        )
        self.add_change()

        credit_data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            category,
            "date_joined",
            "ascending",
        )
        costs = self.generate_cost_data(entity=category)
        language_choices = get_report_language_choices({"category": category})

        self.assertEqual(credit_data, [])
        self.assertEqual(costs["total"]["count"], 0)
        self.assertEqual(len(language_choices), 1)

    def test_counts_one(self) -> None:
        self.add_change()
        data = generate_counts(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            "date_joined",
            "ascending",
            component=self.component,
        )
        self.assertEqual(data, self.counts_data)
        data = generate_counts(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "cs",
            "date_joined",
            "ascending",
            component=self.component,
        )
        self.assertEqual(data, self.counts_data)

    def test_counts_include_child_category_components(self) -> None:
        parent = self.move_component_to_child_category()
        self.add_change()

        data = generate_counts(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "cs",
            "date_joined",
            "ascending",
            category=parent,
        )

        self.assertEqual(data, self.counts_data)

    def test_counts_unique_repeated_edits(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "Nazdar svete 2!\n")
        self.edit_unit("Hello, world!\n", "Nazdar svete 3!\n")

        data = self.generate_count_data()

        self.assertEqual(data[0]["count"], 2)
        self.assertEqual(data[0]["count_new"], 1)
        self.assertEqual(data[0]["count_edit"], 1)
        self.assertEqual(data[0]["words"], 4)
        self.assertEqual(data[0]["words_new"], 2)
        self.assertEqual(data[0]["words_edit"], 2)

    def test_counts_all_repeated_edits(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "Nazdar svete 2!\n")
        self.edit_unit("Hello, world!\n", "Nazdar svete 3!\n")

        data = self.generate_count_data(CountsReportsForm.COUNTING_MODE_ALL)

        self.assertEqual(data[0]["count"], 3)
        self.assertEqual(data[0]["count_new"], 1)
        self.assertEqual(data[0]["count_edit"], 2)
        self.assertEqual(data[0]["words"], 6)
        self.assertEqual(data[0]["words_new"], 2)
        self.assertEqual(data[0]["words_edit"], 4)

    def test_counts_unique_repeated_approvals(self) -> None:
        user = User.objects.create(
            username="approvalbase",
            email="approval-base@example.org",
            password=TESTPASSWORD,
            full_name="Approval Base",
        )
        self.change_unit("Nazdar svete!\n", user=user)
        self.change_unit("Nazdar svete 2!\n", user=self.user, state=STATE_APPROVED)
        self.change_unit("Nazdar svete 3!\n", user=self.user, state=STATE_APPROVED)

        data = generate_counts(
            self.user,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            "date_joined",
            "ascending",
            component=self.component,
        )

        self.assertEqual(data[0]["count"], 1)
        self.assertEqual(data[0]["count_approve"], 1)
        self.assertEqual(data[0]["words"], 2)
        self.assertEqual(data[0]["words_approve"], 2)

    def test_counts_unique_per_user(self) -> None:
        user = User.objects.create(
            username="uniqueuser",
            email="unique-user@example.org",
            password=TESTPASSWORD,
            full_name="Unique User",
        )
        self.change_unit("Nazdar svete!\n", user=self.user)
        self.change_unit("Nazdar svete 2!\n", user=self.user)
        self.change_unit("Nazdar svete 3!\n", user=user)
        self.change_unit("Nazdar svete 4!\n", user=user)

        data = {item["email"]: item for item in self.generate_count_data()}

        self.assertEqual(data[self.user.email]["count"], 2)
        self.assertEqual(data[self.user.email]["count_new"], 1)
        self.assertEqual(data[self.user.email]["count_edit"], 1)
        self.assertEqual(data[user.email]["count"], 1)
        self.assertEqual(data[user.email]["count_edit"], 1)

    def test_cost_estimate_exact_memory(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        self.add_memory(unit.source)

        data = self.generate_cost_data()
        buckets = {bucket["slug"]: bucket for bucket in data["buckets"]}

        self.assertEqual(buckets["tm_100"]["count"], 1)
        self.assertEqual(buckets["tm_100"]["words"], unit.num_words)
        self.assertEqual(buckets["tm_100"]["cost"], "0")

    def test_cost_estimate_fuzzy_memory(self) -> None:
        self.add_memory("Thank you for using Weblate!")

        data = self.generate_cost_data(threshold=MIN_COST_ESTIMATE_TM_THRESHOLD)
        buckets = {bucket["slug"]: bucket for bucket in data["buckets"]}

        self.assertEqual(buckets["tm_fuzzy"]["count"], 1)
        self.assertEqual(buckets["tm_100"]["count"], 0)

    def test_cost_estimate_needs_editing(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        Unit.objects.filter(pk=unit.pk).update(state=STATE_FUZZY)

        data = self.generate_cost_data()
        buckets = {bucket["slug"]: bucket for bucket in data["buckets"]}

        self.assertEqual(buckets["needs_editing"]["count"], 1)

    def test_cost_estimate_repetition_precedes_memory(self) -> None:
        unit = self.get_unit("Thank you for using Weblate.")
        self.add_memory(unit.source)
        self.create_po(project=self.project, name="Other")

        data = self.generate_cost_data(entity=self.project)
        buckets = {bucket["slug"]: bucket for bucket in data["buckets"]}

        self.assertEqual(buckets["tm_100"]["count"], 1)
        self.assertGreaterEqual(buckets["repetition"]["count"], 1)

    def test_cost_estimate_includes_child_category_components(self) -> None:
        parent = self.move_component_to_child_category()

        data = self.generate_cost_data(entity=parent)

        self.assertGreater(data["total"]["count"], 0)

    def test_cost_estimate_plural_match_uses_weakest_form(self) -> None:
        def fake_fetch_machinery_matches(*, units, threshold, **kwargs):
            result = {}
            for unit in units:
                if unit.source.startswith("Orangutan"):
                    unit.machinery = {
                        "quality": [100, 0 if threshold == 100 else 80],
                        "translation": ["", ""],
                        "origin": [None, None],
                    }
                    result[unit.id] = unit.machinery
            return result

        with patch(
            "weblate.trans.views.reports.fetch_machinery_matches",
            side_effect=fake_fetch_machinery_matches,
        ):
            data = self.generate_cost_data()

        buckets = {bucket["slug"]: bucket for bucket in data["buckets"]}
        self.assertEqual(buckets["tm_100"]["count"], 0)
        self.assertGreater(buckets["tm_fuzzy"]["count"], 0)

    def test_cost_estimate_does_not_modify_units(self) -> None:
        unit_targets = {
            pk: (target, state)
            for pk, target, state in Unit.objects.filter(
                translation=self.translation
            ).values_list("pk", "target", "state")
        }
        change_count = Change.objects.count()
        pending_count = PendingUnitChange.objects.count()
        suggestion_count = Suggestion.objects.count()

        self.generate_cost_data()

        self.assertEqual(
            {
                pk: (target, state)
                for pk, target, state in Unit.objects.filter(
                    translation=self.translation
                ).values_list("pk", "target", "state")
            },
            unit_targets,
        )
        self.assertEqual(Change.objects.count(), change_count)
        self.assertEqual(PendingUnitChange.objects.count(), pending_count)
        self.assertEqual(Suggestion.objects.count(), suggestion_count)


class ReportsComponentTest(BaseReportsTest):
    def get_kwargs(self):
        return {"path": self.component.get_url_path()}

    def post_report(self, url, params, style="json", follow=False):
        existing = set(Report.objects.values_list("pk", flat=True))
        response = self.client.post(url, params, follow=follow)
        report = Report.objects.exclude(pk__in=existing).first()
        if report is None:
            return response
        return self.client.get(reverse(f"api:report-{style}", args=[report.pk]))

    def get_credits(self, style, follow=False, **kwargs):
        self.add_change()
        params = {
            "style": style,
            "period": "01/01/2000 - 01/01/2100",
            "sort_by": "count",
            "sort_order": "descending",
        }
        params.update(kwargs)
        return self.post_report(
            reverse("credits", kwargs=self.get_kwargs()), params, style, follow
        )

    def test_credits_view_json(self) -> None:
        response = self.get_credits("json")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [
                {
                    "Czech": [
                        {
                            "email": "weblate@example.org",
                            "full_name": "Weblate <b>Test</b>",
                            "username": "testuser",
                            "change_count": 1,
                            "date_joined": self.user.date_joined.isoformat(),
                        }
                    ]
                }
            ],
        )

    def test_credits_view_rst(self) -> None:
        response = self.get_credits("rst")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(
            response.content.decode().strip(),
            """
* Czech

    * Weblate <b>Test</b> (testuser) <weblate@example.org> - 1
""".strip(),
        )

    def test_credits_view_html(self) -> None:
        response = self.get_credits("html")
        self.assertEqual(response.status_code, 200)
        self.assertHTMLEqual(
            response.content.decode(),
            "<table><tbody>\n"
            "<tr>\n<th>Czech</th>\n"
            '<td><ul><li><a href="mailto:weblate@example.org">'
            "Weblate &lt;b&gt;Test&lt;/b&gt; (testuser)</a> - 1</li></ul></td>\n</tr>\n"
            "</tbody></table>",
        )

    def test_credits_blank_period(self) -> None:
        period = ""
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(
            response, "Error in parameter period: This field is required."
        )

    def test_credits_invalid_start(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = f"{start.strftime('%m/%d/%Y')}invalid - {end.strftime('%m/%d/%Y')}"
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_credits_invalid_end(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}invalid"
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_credits_inverse_daterange(self) -> None:
        start = timezone.now()
        end = start - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(
            response,
            "Error in parameter period: The starting date has to be before the ending date.",
        )

    def get_counts(self, style, follow=False, **kwargs):
        self.add_change()
        params = {
            "style": style,
            "period": "01/01/2000 - 01/01/2100",
            "sort_by": "count",
            "sort_order": "descending",
        }
        params.update(kwargs)
        return self.post_report(
            reverse("counts", kwargs=self.get_kwargs()), params, style, follow
        )

    def get_costs(self, style, follow=False, **kwargs):
        params = {
            "style": style,
            "q": "state:<translated",
            "base_rate": "0.10",
            "tm_threshold": "80",
            "rate_new": "100",
            "rate_needs_editing": "50",
            "rate_tm_100": "0",
            "rate_tm_fuzzy": "50",
            "rate_repetition": "0",
        }
        params.update(kwargs)
        return self.post_report(
            reverse("costs", kwargs=self.get_kwargs()), params, style, follow
        )

    def test_counts_view_json(self) -> None:
        response = self.get_counts("json")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), self.counts_data)

    def test_costs_view_json(self) -> None:
        response = self.get_costs("json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["base_rate"], "0.1")
        self.assertEqual(data["threshold"], 80)
        self.assertEqual(
            [bucket["slug"] for bucket in data["buckets"]],
            ["repetition", "tm_100", "tm_fuzzy", "needs_editing", "new"],
        )

    def test_costs_view_html(self) -> None:
        response = self.get_costs("html")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New strings")
        self.assertContains(response, "Total")

    def test_costs_requires_report_permission(self) -> None:
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        response = self.get_costs("json")
        self.assertEqual(response.status_code, 403)

    def test_costs_invalid_threshold(self) -> None:
        response = self.get_costs("json", tm_threshold="200", follow=True)
        self.assertContains(
            response,
            "Error in parameter tm_threshold: Ensure this value is less than or equal to 100.",
        )

        response = self.get_costs("json", tm_threshold="1", follow=True)
        self.assertContains(
            response,
            "Error in parameter tm_threshold: Ensure this value is greater than or equal to 75.",
        )

    def test_counts_view_30days(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), self.counts_data)

    def test_counts_view_this_month(self) -> None:
        end = timezone.now().replace(day=1) + timedelta(days=31)
        end = end.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), self.counts_data)

    def test_counts_view_month(self) -> None:
        end = timezone.now().replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), [])

    def test_counts_view_year(self) -> None:
        year = timezone.now().year - 1
        # ruff: ignore[call-datetime-without-tzinfo]
        end = timezone.make_aware(datetime(year, 12, 31))
        # ruff: ignore[call-datetime-without-tzinfo]
        start = timezone.make_aware(datetime(year, 1, 1))
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), [])

    def test_counts_view_this_year(self) -> None:
        year = timezone.now().year
        # ruff: ignore[call-datetime-without-tzinfo]
        end = timezone.make_aware(datetime(year, 12, 31))
        # ruff: ignore[call-datetime-without-tzinfo]
        start = timezone.make_aware(datetime(year, 1, 1))
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), self.counts_data)

    def test_counts_view_rst(self) -> None:
        response = self.get_counts("rst")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertContains(response, "Weblate <b>Test</b>")
        self.assertContains(response, "weblate@example.org")

    def test_counts_view_html(self) -> None:
        response = self.get_counts("html")
        self.assertEqual(response.status_code, 200)
        self.assertHTMLEqual(
            response.content.decode(),
            f"""
<table>
    <tr>
        <th>Name</th>
        <th>Email</th>
        <th>Date joined</th>
        <th>Count total</th>
        <th>Edits total</th>
        <th>Source words total</th>
        <th>Source chars total</th>
        <th>Target words total</th>
        <th>Target chars total</th>
        <th>Count new</th>
        <th>Edits new</th>
        <th>Source words new</th>
        <th>Source chars new</th>
        <th>Target words new</th>
        <th>Target chars new</th>
        <th>Count approved</th>
        <th>Edits approved</th>
        <th>Source words approved</th>
        <th>Source chars approved</th>
        <th>Target words approved</th>
        <th>Target chars approved</th>
        <th>Count edited</th>
        <th>Edits edited</th>
        <th>Source words edited</th>
        <th>Source chars edited</th>
        <th>Target words edited</th>
        <th>Target chars edited</th>
    </tr>
    <tr>
        <td>Weblate &lt;b&gt;Test&lt;/b&gt;</td>
        <td>weblate@example.org</td>
        <td>{self.user.date_joined.isoformat()}</td>
        <td>1</td>
        <td>14</td>
        <td>2</td>
        <td>14</td>
        <td>2</td>
        <td>14</td>
        <td>1</td>
        <td>14</td>
        <td>2</td>
        <td>14</td>
        <td>2</td>
        <td>14</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
        <td>0</td>
    </tr>
</table>
""",
        )

    def test_counts_blank_period(self) -> None:
        period = ""
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(
            response, "Error in parameter period: This field is required."
        )

    def test_counts_invalid_start(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = f"{start.strftime('%m/%d/%Y')}invalid - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_counts_invalid_end(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}invalid"
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_counts_inverse_daterange(self) -> None:
        start = timezone.now()
        end = start - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(
            response,
            "Error in parameter period: The starting date has to be before the ending date.",
        )

    def test_counts_invalid_sort_order(self) -> None:
        response = self.get_counts("json", sort_order="editing", follow=True)
        self.assertContains(
            response,
            "Error in parameter sort_order: Select a valid choice. editing is not one of the available choices.",
        )

    def test_counts_invalid_sort_by(self) -> None:
        response = self.get_counts("json", sort_by="-", follow=True)
        self.assertContains(
            response,
            "Error in parameter sort_by: Select a valid choice. - is not one of the available choices.",
        )

    def test_counts_invalid_counting_mode(self) -> None:
        response = self.get_counts("json", counting_mode="-", follow=True)
        self.assertContains(
            response,
            "Error in parameter counting_mode: Select a valid choice. - is not one of the available choices.",
        )

    def create_test_sort_data(self) -> None:
        user1 = User.objects.create(
            username="customtestuser1",
            email="custom-weblate-1@example.org",
            password=TESTPASSWORD,
            full_name="Weblate Test 1",
            date_joined=datetime(2025, 1, 1, tzinfo=UTC),
        )
        user2 = User.objects.create(
            username="customtestuser2",
            email="custom-weblate-2@example.org",
            password=TESTPASSWORD,
            full_name="Weblate Test 2",
            date_joined=datetime(2025, 2, 1, tzinfo=UTC),
        )
        user3 = User.objects.create(
            username="customtestuser3",
            email="custom-weblate-3@example.org",
            password=TESTPASSWORD,
            is_superuser=True,
            full_name="Weblate Test 3",
            date_joined=datetime(2025, 3, 1, tzinfo=UTC),
        )

        self.client.login(username=user1.username, password="testpassword")
        self.edit_unit("Hello, world!\n", "Ciao mondo!\n")
        self.edit_unit("Hello, world!\n", "Halo, Dunia!")

        self.client.login(username=user2.username, password="testpassword")
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.edit_unit("Hello, world!\n", "Hallo wereld!\n")
        self.edit_unit("Hello, world!\n", "Nazdar svete! 2\n")

        self.client.login(username=user3.username, password="testpassword")
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

    def test_counts_sorting(self) -> None:
        self.create_test_sort_data()
        expected_count1 = {
            "name": "Weblate Test 1",
            "email": "custom-weblate-1@example.org",
            "date_joined": "2025-01-01T00:00:00+00:00",
            "t_chars": 25,
            "t_words": 4,
            "chars": 28,
            "words": 4,
            "edits": 20,
            "count": 2,
            "t_chars_new": 12,
            "t_words_new": 2,
            "chars_new": 14,
            "words_new": 2,
            "edits_new": 12,
            "count_new": 1,
            "t_chars_approve": 0,
            "t_words_approve": 0,
            "chars_approve": 0,
            "words_approve": 0,
            "edits_approve": 0,
            "count_approve": 0,
            "t_chars_edit": 13,
            "t_words_edit": 2,
            "chars_edit": 14,
            "words_edit": 2,
            "edits_edit": 8,
            "count_edit": 1,
        }
        expected_count2 = {
            "name": "Weblate Test 2",
            "email": "custom-weblate-2@example.org",
            "date_joined": "2025-02-01T00:00:00+00:00",
            "t_chars": 44,
            "t_words": 7,
            "chars": 42,
            "words": 6,
            "edits": 31,
            "count": 3,
            "t_chars_new": 0,
            "t_words_new": 0,
            "chars_new": 0,
            "words_new": 0,
            "edits_new": 0,
            "count_new": 0,
            "t_chars_approve": 0,
            "t_words_approve": 0,
            "chars_approve": 0,
            "words_approve": 0,
            "edits_approve": 0,
            "count_approve": 0,
            "t_chars_edit": 44,
            "t_words_edit": 7,
            "chars_edit": 42,
            "words_edit": 6,
            "edits_edit": 31,
            "count_edit": 3,
        }
        expected_count3 = {
            "name": "Weblate Test 3",
            "email": "custom-weblate-3@example.org",
            "date_joined": "2025-03-01T00:00:00+00:00",
            "t_chars": 14,
            "t_words": 2,
            "chars": 14,
            "words": 2,
            "edits": 2,
            "count": 1,
            "t_chars_new": 0,
            "t_words_new": 0,
            "chars_new": 0,
            "words_new": 0,
            "edits_new": 0,
            "count_new": 0,
            "t_chars_approve": 0,
            "t_words_approve": 0,
            "chars_approve": 0,
            "words_approve": 0,
            "edits_approve": 0,
            "count_approve": 0,
            "t_chars_edit": 14,
            "t_words_edit": 2,
            "chars_edit": 14,
            "words_edit": 2,
            "edits_edit": 2,
            "count_edit": 1,
        }

        url = reverse("counts", kwargs=self.get_kwargs())
        params = {
            "style": "json",
            "period": "01/01/2000 - 01/01/2100",
            "counting_mode": CountsReportsForm.COUNTING_MODE_ALL,
        }

        response = self.post_report(
            url, {**params, "sort_by": "count", "sort_order": "descending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [expected_count2, expected_count1, expected_count3],
        )

        response = self.post_report(
            url, {**params, "sort_by": "count", "sort_order": "ascending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [expected_count3, expected_count1, expected_count2],
        )

        response = self.post_report(
            url, {**params, "sort_by": "date_joined", "sort_order": "ascending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [expected_count1, expected_count2, expected_count3],
        )

        response = self.post_report(
            url, {**params, "sort_by": "date_joined", "sort_order": "descending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [expected_count3, expected_count2, expected_count1],
        )

    def test_counts_sorting_unique(self) -> None:
        user1 = User.objects.create(
            username="unique_sort_user1",
            email="unique-sort-1@example.org",
            password=TESTPASSWORD,
            full_name="Unique Sort 1",
        )
        user2 = User.objects.create(
            username="unique_sort_user2",
            email="unique-sort-2@example.org",
            password=TESTPASSWORD,
            full_name="Unique Sort 2",
        )
        self.change_unit("Nazdar svete!\n", user=user1)
        self.change_unit("Nazdar svete 2!\n", user=user1)
        self.change_unit("Nazdar svete 3!\n", user=user2)

        response = self.post_report(
            reverse("counts", kwargs=self.get_kwargs()),
            {
                "style": "json",
                "period": "01/01/2000 - 01/01/2100",
                "sort_by": "count",
                "sort_order": "descending",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([item["email"] for item in data], [user1.email, user2.email])
        self.assertEqual([item["count"] for item in data], [2, 1])

    def test_credits_sorting(self) -> None:
        self.create_test_sort_data()
        expected_credit1 = {
            "email": "custom-weblate-1@example.org",
            "username": "customtestuser1",
            "full_name": "Weblate Test 1",
            "change_count": 2,
            "date_joined": "2025-01-01T00:00:00+00:00",
        }
        expected_credit2 = {
            "email": "custom-weblate-2@example.org",
            "username": "customtestuser2",
            "full_name": "Weblate Test 2",
            "change_count": 3,
            "date_joined": "2025-02-01T00:00:00+00:00",
        }
        expected_credit3 = {
            "email": "custom-weblate-3@example.org",
            "username": "customtestuser3",
            "full_name": "Weblate Test 3",
            "change_count": 1,
            "date_joined": "2025-03-01T00:00:00+00:00",
        }

        url = reverse("credits", kwargs=self.get_kwargs())
        params = {"style": "json", "period": "01/01/2000 - 01/01/2100"}

        response = self.post_report(
            url, {**params, "sort_by": "count", "sort_order": "descending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [{"Czech": [expected_credit2, expected_credit1, expected_credit3]}],
        )

        response = self.post_report(
            url, {**params, "sort_by": "count", "sort_order": "ascending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [{"Czech": [expected_credit3, expected_credit1, expected_credit2]}],
        )

        response = self.post_report(
            url, {**params, "sort_by": "date_joined", "sort_order": "ascending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [{"Czech": [expected_credit1, expected_credit2, expected_credit3]}],
        )

        response = self.post_report(
            url, {**params, "sort_by": "date_joined", "sort_order": "descending"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [{"Czech": [expected_credit3, expected_credit2, expected_credit1]}],
        )


class ReportsProjectTest(ReportsComponentTest):
    def get_kwargs(self):
        return {"path": self.project.get_url_path()}


class ReportsGlobalTest(ReportsComponentTest):
    def get_kwargs(self):
        return {}


class ReportsCategoryTest(ReportsComponentTest):
    def setUp(self) -> None:
        super().setUp()
        self.setup_category()

    def setup_category(self) -> None:
        self.component.category = self.create_category(project=self.project)
        self.component.save()
        self.category = self.component.category

    def get_kwargs(self) -> dict[str, tuple]:
        return {"path": self.category.get_url_path()}
