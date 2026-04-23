# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.template import Context, Template
from django.test import SimpleTestCase

from weblate.accounts.templatetags.authnames import get_auth_name, get_auth_params
from weblate.accounts.templatetags.urlformat import urlformat


class TemplateTagsTestCase(SimpleTestCase):
    def test_add_site_url_filter(self) -> None:
        template = Template("""
                {% load site_url %}
                <html><body>
                {% filter add_site_url %}
                <p>
                    text:
                    <a href="/foo"><span>Foo</span></a>
                </p>
                {% endfilter %}
                <p>
                {% filter add_site_url %}
                    other&amp;
                {% endfilter %}
                </p>
                </body>
                </html>
            """)
        self.assertHTMLEqual(
            """
            <html>
            <body>
                <p>
                    text:
                    <a href="http://example.com/foo">
                        <span>
                            Foo
                        </span>
                    </a>
                </p>
                <p>other&amp;</p>
            </body>
            </html>
            """,
            template.render(Context()),
        )

    def test_urlformat(self) -> None:
        self.assertEqual(urlformat("https://weblate.org/"), "weblate.org")
        self.assertEqual(urlformat("https://weblate.org/user/"), "weblate.org/user")
        self.assertEqual(
            urlformat("https://weblate.org/user/xxxxxxxxxxxxxxxxxxxxxxxxx"),
            "weblate.org",
        )

    def test_microsoft_entra_defaults(self) -> None:
        self.assertEqual(get_auth_name("azuread-oauth2"), "Microsoft")
        self.assertEqual(
            get_auth_params("azuread-tenant-oauth2")["image"],
            "microsoft.svg",
        )
