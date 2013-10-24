from django.test import LiveServerTestCase
from django.utils.unittest import SkipTest
from selenium import webdriver
from django.core.urlresolvers import reverse
import os
import new
import json
import httplib
import base64

IN_TRAVIS = 'TRAVIS_JOB_ID' in os.environ
DO_SELENIUM = 'TRAVIS_SELENIUM' in os.environ

# Check whether we should run Selenium tests
DO_SELENIUM = (
    'SAUCE_USERNAME' in os.environ
    and 'SAUCE_ACCESS_KEY' in os.environ
    and (not IN_TRAVIS or (IN_TRAVIS and DO_SELENIUM))
)


class SeleniumTests(LiveServerTestCase):
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
            '/rest/v1/%s/jobs/%s' % (
                self.username, self.driver.session_id
            ),
            body_content,
            headers={"Authorization": "Basic %s" % self.sauce_auth}
        )
        result = connection.getresponse()
        return result.status == 200

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()

        errors = result.errors
        failures = result.failures
        super(SeleniumTests, self).run(result)

        if DO_SELENIUM:
            self.set_test_status(
                (errors == result.errors and failures == result.failures)
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
                    'python-%s' % os.environ['TRAVIS_PYTHON_VERSION'],
                    'django-%s' % os.environ['DJANGO_VERSION'],
                    os.environ['TRAVIS_DATABASE'],
                    'CI'
                ]

            # Use Sauce connect
            cls.username = os.environ['SAUCE_USERNAME']
            cls.key = os.environ['SAUCE_ACCESS_KEY']
            cls.sauce_auth = base64.encodestring(
                '%s:%s' % (cls.username, cls.key)
            )[:-1]
            hub_url = "%s:%s@localhost:4445" % (cls.username, cls.key)
            cls.driver = webdriver.Remote(
                desired_capabilities=cls.caps,
                command_executor="http://%s/wd/hub" % hub_url
            )
            jobid = cls.driver.session_id
            print "Sauce Labs job: https://saucelabs.com/jobs/%s" % jobid
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
        self.driver.get('%s%s' % (self.live_server_url, reverse('login')))

        username_input = self.driver.find_element_by_id('id_username')
        username_input.send_keys("myuser")
        password_input = self.driver.find_element_by_id('id_password')
        password_input.send_keys("secret")
        self.driver.find_element_by_xpath('//input[@value="Login"]').click()

        # We should end up on login page as user was invalid
        self.driver.find_element_by_name('username')


# What other platforms we want to test
EXTRA_PLATFORMS = {
    'Chrome': {
        'browserName': 'chrome',
        'platform': 'XP',
    },
    # Following browsers do not work correctly store cookies with Sauce labs:
    # http://support.saucelabs.com/entries/20629691
    #'Opera': {
    #    'browserName': 'opera',
    #    'platform': 'WIN7',
    #},
    #'MSIE10': {
    #    'browserName': 'internet explorer',
    #    'version': '10',
    #    'platform': 'WIN8',
    #},
    #'MSIE9': {
    #    'browserName': 'internet explorer',
    #    'version': '9',
    #    'platform': 'VISTA',
    #},
}


def create_extra_classes():
    '''
    Create classes for testing with other browsers
    '''
    classes = {}
    for platform in EXTRA_PLATFORMS:
        classdict = dict(SeleniumTests.__dict__)
        name = '%s_%s' % (
            SeleniumTests.__name__,
            platform
        )
        classdict.update({
            'caps': EXTRA_PLATFORMS[platform],
        })
        classes[name] = new.classobj(name, (SeleniumTests,), classdict)

    globals().update(classes)

create_extra_classes()
