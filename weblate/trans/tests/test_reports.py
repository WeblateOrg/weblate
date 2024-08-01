# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from weblate.trans.models.category import Category
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.views.reports import generate_counts, generate_credits

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
        self.maxDiff = None

    def add_change(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")


class ReportsTest(BaseReportsTest):
    def test_credits_empty(self) -> None:
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            self.component,
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
                        "change_count": expected_count,
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
        )
        self.assertEqual(data, expected)
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "cs",
            self.component,
        )
        self.assertEqual(data, expected)
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "de",
            self.component,
        )
        self.assertEqual(data, [])

    def test_credits_more(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete2!\n")
        self.test_credits_one(expected_count=2)

    def test_counts_one(self) -> None:
        self.add_change()
        data = generate_counts(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "",
            component=self.component,
        )
        self.assertEqual(data, COUNTS_DATA)
        data = generate_counts(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            "cs",
            component=self.component,
        )
        self.assertEqual(data, COUNTS_DATA)


class ReportsComponentTest(BaseReportsTest):
    def get_kwargs(self):
        return {"path": self.component.get_url_path()}

    def get_credits(self, style, follow=False, **kwargs):
        self.add_change()
        params = {"style": style, "period": "01/01/2000 - 01/01/2100"}
        params.update(kwargs)
        return self.client.post(
            reverse("credits", kwargs=self.get_kwargs()), params, follow=follow
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
                            "change_count": 1,
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

    * Weblate <b>Test</b> <weblate@example.org> (1)
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
            "Weblate &lt;b&gt;Test&lt;/b&gt;</a> (1)</li></ul></td>\n</tr>\n"
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
        period = "{}invalid - {}".format(
            start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        )
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_credits_invalid_end(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = "{} - {}invalid".format(
            start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        )
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_credits_inverse_daterange(self) -> None:
        start = timezone.now()
        end = start - timedelta(days=1)
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_credits("json", period=period, follow=True)
        self.assertContains(
            response,
            "Error in parameter period: The starting date has to be before the ending date.",
        )

    def get_counts(self, style, follow=False, **kwargs):
        self.add_change()
        params = {"style": style, "period": "01/01/2000 - 01/01/2100"}
        params.update(kwargs)
        return self.client.post(
            reverse("counts", kwargs=self.get_kwargs()), params, follow=follow
        )

    def test_counts_view_json(self) -> None:
        response = self.get_counts("json")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_30days(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_this_month(self) -> None:
        end = timezone.now().replace(day=1) + timedelta(days=31)
        end = end.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_month(self) -> None:
        end = timezone.now().replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), [])

    def test_counts_view_year(self) -> None:
        year = timezone.now().year - 1
        end = timezone.make_aware(datetime(year, 12, 31))  # noqa: DTZ001
        start = timezone.make_aware(datetime(year, 1, 1))  # noqa: DTZ001
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), [])

    def test_counts_view_this_year(self) -> None:
        year = timezone.now().year
        end = timezone.make_aware(datetime(year, 12, 31))  # noqa: DTZ001
        start = timezone.make_aware(datetime(year, 1, 1))  # noqa: DTZ001
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_counts("json", period=period)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

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
            """
<table>
    <tr>
        <th>Name</th>
        <th>Email</th>
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
        period = "{}invalid - {}".format(
            start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        )
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_counts_invalid_end(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=30)
        period = "{} - {}invalid".format(
            start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        )
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(response, "Error in parameter period: Invalid date!")

    def test_counts_inverse_daterange(self) -> None:
        start = timezone.now()
        end = start - timedelta(days=1)
        period = "{} - {}".format(start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y"))
        response = self.get_counts("json", period=period, follow=True)
        self.assertContains(
            response,
            "Error in parameter period: The starting date has to be before the ending date.",
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
        self.category = self.create_category()

    def create_category(self) -> None:
        category = Category.objects.create(
            name="test category", slug="test-category", project=self.project
        )
        self.component.category = category
        self.component.save()
        return category

    def get_kwargs(self) -> dict[str, tuple]:
        return {"path": self.category.get_url_path()}
