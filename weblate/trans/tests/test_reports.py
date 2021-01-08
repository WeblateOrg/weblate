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


from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.views.reports import generate_counts, generate_credits

COUNTS_DATA = [
    {
        "count": 1,
        "count_edit": 0,
        "count_new": 1,
        "name": "Weblate Test",
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
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def add_change(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")


class ReportsTest(BaseReportsTest):
    def test_credits_empty(self):
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            translation__component=self.component,
        )
        self.assertEqual(data, [])

    def test_credits_one(self, expected_count=1):
        self.add_change()
        data = generate_credits(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            translation__component=self.component,
        )
        self.assertEqual(
            data, [{"Czech": [("weblate@example.org", "Weblate Test", expected_count)]}]
        )

    def test_credits_more(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete2!\n")
        self.test_credits_one(expected_count=2)

    def test_counts_one(self):
        self.add_change()
        data = generate_counts(
            None,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=1),
            component=self.component,
        )
        self.assertEqual(data, COUNTS_DATA)


class ReportsComponentTest(BaseReportsTest):
    def get_kwargs(self):
        return self.kw_component

    def get_credits(self, style):
        self.add_change()
        return self.client.post(
            reverse("credits", kwargs=self.get_kwargs()),
            {
                "period": "",
                "style": style,
                "start_date": "2000-01-01",
                "end_date": "2100-01-01",
            },
        )

    def test_credits_view_json(self):
        response = self.get_credits("json")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            [{"Czech": [["weblate@example.org", "Weblate Test", 1]]}],
        )

    def test_credits_view_rst(self):
        response = self.get_credits("rst")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content.decode(),
            "\n\n* Czech\n\n    * Weblate Test <weblate@example.org> (1)\n\n",
        )

    def test_credits_view_html(self):
        response = self.get_credits("html")
        self.assertEqual(response.status_code, 200)
        self.assertHTMLEqual(
            response.content.decode(),
            "<table>\n"
            "<tr>\n<th>Czech</th>\n"
            '<td><ul><li><a href="mailto:weblate@example.org">'
            "Weblate Test</a> (1)</li></ul></td>\n</tr>\n"
            "</table>",
        )

    def get_counts(self, style, **kwargs):
        self.add_change()
        params = {
            "style": style,
            "period": "",
            "start_date": "2000-01-01",
            "end_date": "2100-01-01",
        }
        params.update(kwargs)
        return self.client.post(reverse("counts", kwargs=self.get_kwargs()), params)

    def test_counts_view_json(self):
        response = self.get_counts("json")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_30days(self):
        response = self.get_counts("json", period="30days")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_this_month(self):
        response = self.get_counts("json", period="this-month")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_month(self):
        response = self.get_counts("json", period="month")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), [])

    def test_counts_view_year(self):
        response = self.get_counts("json", period="year")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), [])

    def test_counts_view_this_year(self):
        response = self.get_counts("json", period="this-year")
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), COUNTS_DATA)

    def test_counts_view_rst(self):
        response = self.get_counts("rst")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "weblate@example.org")

    def test_counts_view_html(self):
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
        <td>Weblate Test</td>
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


class ReportsProjectTest(ReportsComponentTest):
    def get_kwargs(self):
        return self.kw_project


class ReportsGlobalTest(ReportsComponentTest):
    def get_kwargs(self):
        return {}
