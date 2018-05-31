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

from __future__ import print_function
from unittest import SkipTest
import time
import os
import json
from contextlib import contextmanager
from base64 import b64encode
from six.moves.http_client import HTTPConnection
import django
from django.test.utils import override_settings
from django.urls import reverse
from django.core import mail
try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        WebDriverException, ElementNotVisibleException
    )
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support.expected_conditions import staleness_of
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.test_models import BaseLiveServerTestCase
from weblate.trans.tests.utils import create_test_user

# Check whether we should run Selenium tests
DO_SELENIUM = (
    'DO_SELENIUM' in os.environ and
    'SAUCE_USERNAME' in os.environ and
    'SAUCE_ACCESS_KEY' in os.environ and
    HAS_SELENIUM
)


class SeleniumTests(BaseLiveServerTestCase, RegistrationTestMixin):
    caps = {
        'browserName': 'firefox',
        'platform': 'Windows 10',
    }
    driver = None

    def set_test_status(self, passed=True):
        connection = HTTPConnection("saucelabs.com")
        connection.request(
            'PUT',
            '/rest/v1/{0}/jobs/{1}'.format(
                self.username, self.driver.session_id
            ),
            json.dumps({"passed": passed}),
            headers={"Authorization": "Basic {0}".format(self.sauce_auth)}
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

    @contextmanager
    def wait_for_page_load(self, timeout=30):
        old_page = self.driver.find_element_by_tag_name('html')
        yield
        WebDriverWait(self.driver, timeout).until(
            staleness_of(old_page)
        )

    @classmethod
    def setUpClass(cls):
        if DO_SELENIUM:
            cls.caps['name'] = 'Weblate CI build'
            cls.caps['screenResolution'] = '1024x768'
            # Fill in Travis details in caps
            if 'TRAVIS_JOB_NUMBER' in os.environ:
                cls.caps['tunnel-identifier'] = os.environ['TRAVIS_JOB_NUMBER']
                cls.caps['build'] = os.environ['TRAVIS_BUILD_NUMBER']
                cls.caps['tags'] = [
                    'python-{0}'.format(os.environ['TRAVIS_PYTHON_VERSION']),
                    'django-{0}'.format(django.get_version()),
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
                'Sauce Labs job: https://saucelabs.com/jobs/{0}'.format(jobid)
            )
        super(SeleniumTests, cls).setUpClass()

    def setUp(self):
        if self.driver is None:
            raise SkipTest('Selenium Tests disabled')
        super(SeleniumTests, self).setUp()
        self.driver.get('{0}{1}'.format(self.live_server_url, reverse('home')))
        self.driver.set_window_size(1024, 768)
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        super(SeleniumTests, cls).tearDownClass()
        if cls.driver is not None:
            cls.driver.quit()
            cls.driver = None

    def click(self, element):
        """Wrapper to scroll into element for click"""
        try:
            element.click()
        except ElementNotVisibleException:
            self.actions.move_to_element(element).perform()
            element.click()

    def do_login(self, create=True):
        # login page
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_id('login-button'),
            )

        # Create user
        if create:
            create_test_user()

        # Login
        username_input = self.driver.find_element_by_id('id_username')
        username_input.send_keys('weblate@example.org')
        password_input = self.driver.find_element_by_id('id_password')
        password_input.send_keys('testpassword')

        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_xpath('//input[@value="Login"]')
            )

    def test_failed_login(self):
        self.do_login(create=False)

        # We should end up on login page as user was invalid
        self.driver.find_element_by_id('id_username')

    def test_login(self):
        # Do proper login with new user
        self.do_login()

        # Load profile
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_id('profile-button')
            )

        # Wait for profile to load
        self.driver.find_element_by_id('subscriptions')

        # Finally logout
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_id('logout-button')
            )

        # We should be back on home page
        self.driver.find_element_by_id('suggestions')

    def register_user(self):
        # registration page
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_id('register-button'),
            )

        # Fill in registration form
        self.driver.find_element_by_id(
            'id_email'
        ).send_keys(
            'weblate@example.org'
        )
        self.driver.find_element_by_id(
            'id_username'
        ).send_keys(
            'test-example'
        )
        self.driver.find_element_by_id(
            'id_fullname'
        ).send_keys(
            'Test Example'
        )
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_xpath('//input[@value="Register"]')
            )

        # Wait for registration email
        loops = 0
        while not mail.outbox:
            time.sleep(1)
            loops += 1
            if loops > 20:
                break

        return ''.join(
            (self.live_server_url, self.assert_registration_mailbox())
        )

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_register(self, clear=False):
        """Test registration."""
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
        """Test registration without cookies."""
        self.test_register(True)


# What other platforms we want to test
EXTRA_PLATFORMS = {
    'Chrome': {
        'browserName': 'chrome',
        'platform': 'Windows 10',
    },
}


def create_extra_classes():
    """Create classes for testing with other browsers"""
    classes = {}
    for platform, caps in EXTRA_PLATFORMS.items():
        name = '{0}_{1}'.format(
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
