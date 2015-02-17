from django.test import LiveServerTestCase
from unittest import SkipTest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from django.core.urlresolvers import reverse
from django.core import mail
from django.contrib.auth.models import User
import time
import django
import os
import new
import json
import httplib
import base64

from weblate import appsettings
from weblate.trans.tests.test_views import RegistrationTestMixin

# Check whether we should run Selenium tests
DO_SELENIUM = (
    ('DO_SELENIUM' in os.environ or 'CI_SELENIUM' in os.environ) and
    'SAUCE_USERNAME' in os.environ and
    'SAUCE_ACCESS_KEY' in os.environ
)


class SeleniumTests(LiveServerTestCase, RegistrationTestMixin):
    caps = {
        'browserName': 'firefox',
        'version': '19',
        'platform': 'LINUX',
    }

    def set_test_status(self, passed=True):
        body_content = json.dumps({"passed": passed})
        connection = httplib.HTTPConnection("saucelabs.com")
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
            cls.sauce_auth = base64.encodestring(
                '{}:{}'.format(cls.username, cls.key)
            )[:-1]
            hub_url = "{}:{}@localhost:4445".format(cls.username, cls.key)
            cls.driver = webdriver.Remote(
                desired_capabilities=cls.caps,
                command_executor="http://{}/wd/hub".format(hub_url)
            )
            cls.driver.implicitly_wait(10)
            jobid = cls.driver.session_id
            print 'Sauce Labs job: https://saucelabs.com/jobs/{}'.format(jobid)
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

    def test_login(self):
        # open home page
        self.driver.get('{}{}'.format(self.live_server_url, reverse('home')))

        # login page
        self.driver.find_element_by_id('login-button').click()

        username_input = self.driver.find_element_by_id('id_username')
        username_input.send_keys('testuser')
        password_input = self.driver.find_element_by_id('id_password')
        password_input.send_keys('secret')
        self.driver.find_element_by_xpath('//input[@value="Login"]').click()

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
        self.driver.find_element_by_xpath('//input[@value="Login"]').click()

        # Wait for submit
        time.sleep(1)

        # Load profile
        self.driver.find_element_by_id('profile-button').click()

        # Wait for profile to load
        self.driver.find_element_by_id('subscriptions')

        # Finally logout
        self.driver.find_element_by_id('logout-button').click()

        # We should be back on login page
        self.driver.find_element_by_id('id_username')

    def register_user(self):
        # open home page
        self.driver.get('{}{}'.format(self.live_server_url, reverse('home')))

        # registration page
        self.driver.find_element_by_id('register-button').click()

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
        self.driver.find_element_by_xpath(
            '//input[@value="Register"]'
        ).click()

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

    def test_register(self, clear=False):
        """
        Test registration.
        """
        # We don't want captcha
        appsettings.REGISTRATION_CAPTCHA = False

        url = self.register_user()

        # Delete all cookies
        if clear:
            try:
                self.driver.delete_all_cookies()
            except WebDriverException as error:
                # This usually happens when browser fails to delete some
                # of the cookies for whatever reason.
                print 'Ignoring: {0}'.format(error)

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
        # Restore
        appsettings.REGISTRATION_CAPTCHA = True

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
    'Opera': {
        'browserName': 'opera',
        'platform': 'WIN7',
    },
    'MSIE10': {
        'browserName': 'internet explorer',
        'version': '10',
        'platform': 'WIN8',
    },
    'MSIE9': {
        'browserName': 'internet explorer',
        'version': '9',
        'platform': 'VISTA',
    },
}


def create_extra_classes():
    '''
    Create classes for testing with other browsers
    '''
    classes = {}
    for platform in EXTRA_PLATFORMS:
        classdict = dict(SeleniumTests.__dict__)
        name = '{}_{}'.format(
            platform,
            SeleniumTests.__name__,
        )
        classdict.update({
            'caps': EXTRA_PLATFORMS[platform],
        })
        classes[name] = new.classobj(name, (SeleniumTests,), classdict)

    globals().update(classes)

create_extra_classes()
