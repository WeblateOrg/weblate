# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
"""Testing of template tags."""

import datetime
from unittest import TestCase

from django.utils import timezone
from django.test import SimpleTestCase

from weblate.accounts.models import Profile
from weblate.trans.models import Unit, Component, Translation
from weblate.trans.templatetags.translations import (
    naturaltime, get_location_links
)

TEST_DATA = (
    (0, 'now'),
    (1, 'a second from now'),
    (-1, 'a second ago'),
    (2, '2 seconds from now'),
    (-2, '2 seconds ago'),
    (60, 'a minute from now'),
    (-60, 'a minute ago'),
    (120, '2 minutes from now'),
    (-120, '2 minutes ago'),
    (3600, 'an hour from now'),
    (-3600, 'an hour ago'),
    (3600 * 2, '2 hours from now'),
    (-3600 * 2, '2 hours ago'),
    (3600 * 24, 'tomorrow'),
    (-3600 * 24, 'yesterday'),
    (3600 * 24 * 2, '2 days from now'),
    (-3600 * 24 * 2, '2 days ago'),
    (3600 * 24 * 7, 'a week from now'),
    (-3600 * 24 * 7, 'a week ago'),
    (3600 * 24 * 14, '2 weeks from now'),
    (-3600 * 24 * 14, '2 weeks ago'),
    (3600 * 24 * 30, 'a month from now'),
    (-3600 * 24 * 30, 'a month ago'),
    (3600 * 24 * 60, '2 months from now'),
    (-3600 * 24 * 60, '2 months ago'),
    (3600 * 24 * 365, 'a year from now'),
    (-3600 * 24 * 365, 'a year ago'),
    (3600 * 24 * 365 * 2, '2 years from now'),
    (-3600 * 24 * 365 * 2, '2 years ago'),
)


class NaturalTimeTest(TestCase):
    """Testing of natural time conversion."""
    def test_natural(self):
        now = timezone.now()
        for diff, expected in TEST_DATA:
            testdate = now + datetime.timedelta(seconds=diff)
            result = naturaltime(testdate, now)
            expected = '<span title="{0}">{1}</span>'.format(
                testdate.replace(microsecond=0).isoformat(),
                expected,
            )
            self.assertEqual(
                expected, result,
                'naturaltime({0}) "{1}" != "{2}"'.format(
                    testdate, result, expected
                )
            )


class LocationLinksTest(SimpleTestCase):
    def setUp(self):
        self.unit = Unit(
            translation=Translation(
                component=Component()
            )
        )
        self.profile = Profile()

    def test_empty(self):
        self.assertEqual(
            get_location_links(self.profile, self.unit),
            ''
        )

    def test_numeric(self):
        self.unit.location = '123'
        self.assertEqual(
            get_location_links(self.profile, self.unit),
            'string ID 123'
        )

    def test_filename(self):
        self.unit.location = 'f&oo.bar:123'
        self.assertEqual(
            get_location_links(self.profile, self.unit),
            'f&amp;oo.bar:123'
        )

    def test_filenames(self):
        self.unit.location = 'foo.bar:123,bar.foo:321'
        self.assertEqual(
            get_location_links(self.profile, self.unit),
            'foo.bar:123\nbar.foo:321'
        )

    def test_repowebs(self):
        self.unit.translation.component.repoweb = (
            'http://example.net/%(file)s#L%(line)s'
        )
        self.unit.location = 'foo.bar:123,bar.foo:321'
        self.assertHTMLEqual(
            get_location_links(self.profile, self.unit),
            '''
            <a href="http://example.net/foo.bar#L123" target="_blank"
                rel="noopener noreferrer">
            foo.bar:123
            <i class="fa fa-external-link"></i>
            </a>
            <a href="http://example.net/bar.foo#L321" target="_blank"
                rel="noopener noreferrer">
            bar.foo:321
            <i class="fa fa-external-link"></i>
            </a>
            '''
        )

    def test_repoweb(self):
        self.unit.translation.component.repoweb = (
            'http://example.net/%(file)s#L%(line)s'
        )
        self.unit.location = 'foo.bar:123'
        self.assertHTMLEqual(
            get_location_links(self.profile, self.unit),
            '''
            <a href="http://example.net/foo.bar#L123" target="_blank"
                rel="noopener noreferrer">
            foo.bar:123
            <i class="fa fa-external-link"></i>
            </a>
            '''
        )

    def test_user_url(self):
        self.unit.translation.component.repoweb = (
            'http://example.net/%(file)s#L%(line)s'
        )
        self.profile.editor_link = 'editor://open/?file=%(file)s&line=%(line)s'
        self.unit.location = 'foo.bar:123'
        self.assertHTMLEqual(
            get_location_links(self.profile, self.unit),
            '''
            <a href="editor://open/?file=foo.bar&amp;line=123" target="_blank"
                rel="noopener noreferrer">
            foo.bar:123
            <i class="fa fa-external-link"></i>
            </a>
            '''
        )
