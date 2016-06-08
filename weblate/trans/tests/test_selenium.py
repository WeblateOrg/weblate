# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import print_function
from unittest import SkipTest
import time
import os
import json
from base64 import b64encode
from six.moves.http_client import HTTPConnection
import django
from django.test import LiveServerTestCase
from django.core.urlresolvers import reverse
from django.core import mail
from django.contrib.auth.models import User
try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        WebDriverException, ElementNotVisibleException
    )
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests import OverrideSettings

# Check whether we should run Selenium tests
DO_SELENIUM = (
    'DO_SELENIUM' in os.environ and
    'SAUCE_USERNAME' in os.environ and
    'SAUCE_ACCESS_KEY' in os.environ and
    HAS_SELENIUM
)


class SeleniumTests(LiveServerTestCase, RegistrationTestMixin):
    caps = {
        'browserName': 'firefox',
        'platform': 'Linux',
    }

    def set_test_status(self, passed=True):
        body_content = json.dumps({"passed": passed})
        connection = HTTPConnection("saucelabs.com")
        connection.request(
            'PUT',
            '/rest/v1/{}/jobs/{}'.format(
                self.username, self.driver.session_id
            ),
            body_content,
            headers={"Authorization": "Basic {}".format(self.sauce_auth)}
        )
        result = connection.getresponse()
        return result.status == 200

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()

        errors = len(result.errors)
        failures = len(result.failures)
        super(SeleniumTests, self).run(result)

        if DO_SELENIUM:
            self.set_test_status(
                errors == len(result.errors) and
                failures == len(result.failures)
            )

    @classmethod
    def setUpClass(cls):
        if DO_SELENIUM:
            cls.caps['name'] = 'Weblate CI build'
            # Fill in Travis details in caps
            if 'TRAVIS_JOB_NUMBER' in os.environ:
                cls.caps['tunnel-identifier'] = os.environ['TRAVIS_JOB_NUMBER']
                cls.caps['build'] = os.environ['TRAVIS_BUILD_NUMBER']
                cls.caps['tags'] = [
                    'python-{}'.format(os.environ['TRAVIS_PYTHON_VERSION']),
                    'django-{}'.format(django.get_version()),
                    'CI'
                ]

            # Use Sauce connect
            cls.username = os.environ['SAUCE_USERNAME']
            cls.key = os.environ['SAUCE_ACCESS_KEY']
            cls.sauce_auth = b64encode(
                '{}:{}'.format(cls.username, cls.key).encode('utf-8')
            )
            cls.driver = webdriver.Remote(
                desired_capabilities=cls.caps,
                command_executor="http://{0}:{1}@{2}/wd/hub".format(
                    cls.username,
                    cls.key,
                    'ondemand.saucelabs.com',
                )
            )
            cls.driver.implicitly_wait(10)
            cls.actions = webdriver.ActionChains(cls.driver)
            jobid = cls.driver.session_id
            print(
                'Sauce Labs job: https://saucelabs.com/jobs/{}'.format(jobid)
            )
        super(SeleniumTests, cls).setUpClass()

    def setUp(self):
        if not DO_SELENIUM:
            raise SkipTest('Selenium Tests disabled')
        super(SeleniumTests, self).setUp()

    @classmethod
    def tearDownClass(cls):
        super(SeleniumTests, cls).tearDownClass()
        if DO_SELENIUM:
            cls.driver.quit()

    def expand_navbar(self):
        """Expand navbar if exists"""
        try:
            self.driver.find_element_by_id('navbar-toggle').click()
        except ElementNotVisibleException:
            return

    def click(self, element):
        """Wrapper to scroll into element for click"""
        try:
            element.click()
        except ElementNotVisibleException:
            self.actions.move_to_element(element).perform()
            element.click()

    def test_login(self):
        # open home page
        self.driver.get('{}{}'.format(self.live_server_url, reverse('home')))

        # login page
        self.expand_navbar()
        self.click(
            self.driver.find_element_by_id('login-button'),
        )

        username_input = self.driver.find_element_by_id('id_username')
        username_input.send_keys('testuser')
        password_input = self.driver.find_element_by_id('id_password')
        password_input.send_keys('secret')
        self.click(
            self.driver.find_element_by_xpath('//input[@value="Login"]')
        )

        # We should end up on login page as user was invalid
        self.driver.find_element_by_name('username')

        # Do proper login with new user
        User.objects.create_user(
            'testuser',
            'noreply@weblate.org',
            'testpassword',
            first_name='Test User',
        )
        password_input = self.driver.find_element_by_id('id_password')
        password_input.send_keys('testpassword')
        self.click(
            self.driver.find_element_by_xpath('//input[@value="Login"]')
        )

        # Wait for submit
        time.sleep(1)

        # Load profile
        self.expand_navbar()
        self.click(
            self.driver.find_element_by_id('profile-button')
        )

        # Wait for profile to load
        self.driver.find_element_by_id('subscriptions')

        # Finally logout
        self.expand_navbar()
        self.click(
            self.driver.find_element_by_id('logout-button')
        )

        # We should be back on home page
        self.expand_navbar()
        self.driver.find_element_by_id('suggestions')

    def register_user(self):
        # open home page
        self.driver.get('{}{}'.format(self.live_server_url, reverse('home')))

        # registration page
        self.expand_navbar()
        self.click(
            self.driver.find_element_by_id('register-button'),
        )

        # Fill in registration form
        self.driver.find_element_by_id(
            'id_email'
        ).send_keys(
            'test@example.net'
        )
        self.driver.find_element_by_id(
            'id_username'
        ).send_keys(
            'test-example'
        )
        self.driver.find_element_by_id(
            'id_first_name'
        ).send_keys(
            'Test Example'
        )
        self.click(
            self.driver.find_element_by_xpath('//input[@value="Register"]')
        )

        # Wait for registration email
        loops = 0
        while len(mail.outbox) == 0:
            time.sleep(1)
            loops += 1
            if loops > 20:
                break

        return ''.join(
            (self.live_server_url, self.assert_registration_mailbox())
        )

    @OverrideSettings(REGISTRATION_CAPTCHA=False)
    def test_register(self, clear=False):
        """
        Test registration.
        """
        url = self.register_user()

        # Delete all cookies
        if clear:
            try:
                self.driver.delete_all_cookies()
            except WebDriverException as error:
                # This usually happens when browser fails to delete some
                # of the cookies for whatever reason.
                print('Ignoring: {0}'.format(error))

        # Confirm account
        self.driver.get(url)

        # Check we're logged in
        self.expand_navbar()
        self.assertTrue(
            'Test Example' in
            self.driver.find_element_by_id('profile-button').text
        )

        # Check we got message
        self.assertTrue(
            'You have activated' in
            self.driver.find_element_by_tag_name('body').text
        )

    def test_register_nocookie(self):
        """
        Test registration without cookies.
        """
        self.test_register(True)


# What other platforms we want to test
EXTRA_PLATFORMS = {
    'Chrome': {
        'browserName': 'chrome',
        'platform': 'XP',
    },
    'MSIE9': {
        'browserName': 'internet explorer',
        'version': '9.0',
        'platform': 'Windows 7',
    },
    'Android': {
        'browserName': "android",
        'deviceName': "Android Emulator",
        'device-orientation': "portrait",
    },
}


def create_extra_classes():
    '''
    Create classes for testing with other browsers
    '''
    classes = {}
    for platform, caps in EXTRA_PLATFORMS.items():
        name = '{}_{}'.format(
            platform,
            SeleniumTests.__name__,
        )
        classdict = dict(SeleniumTests.__dict__)
        classdict.update({
            'caps': caps,
        })
        classes[name] = type(name, (SeleniumTests,), classdict)

    globals().update(classes)

create_extra_classes()
