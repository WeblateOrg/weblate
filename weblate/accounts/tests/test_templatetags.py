# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.template import Context, Template
from django.test import SimpleTestCase


class TemplateTagsTestCase(SimpleTestCase):
    def test_simple(self):
        template = Template("""
                {% load site_url %}
                <html><body>
                {% filter add_site_url %}
                    text:
                    <a href="/foo"><span>Foo</span></a>

                {% endfilter %}
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
            </body>
            </html>
            """,
            template.render(Context()),
        )
