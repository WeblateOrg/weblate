from django.test import LiveServerTestCase
from django.utils.unittest import SkipTest
from selenium import webdriver
from django.core.urlresolvers import reverse
import os
import new

# Check whether we should run Selenium tests
DO_SELENIUM = (
    'TEST_SELENIUM' in os.environ
    and 'SAUCE_USERNAME' in os.environ
    and 'SAUCE_ACCESS_KEY' in os.environ
)


class SeleniumTests(LiveServerTestCase):
    caps = {
        'browserName': 'firefox',
        'version': '19',
        'platform': 'LINUX',
    }

    @classmethod
    def setUpClass(cls):
        if DO_SELENIUM:
            cls.caps['name'] = 'Weblate'
            # Fill in Travis details in caps
            if 'TRAVIS_JOB_NUMBER' in os.environ:
                cls.caps['tunnel-identifier'] = os.environ['TRAVIS_JOB_NUMBER']
                cls.caps['build'] = os.environ['TRAVIS_BUILD_NUMBER']
                cls.caps['tags'] = [
                    os.environ['TRAVIS_PYTHON_VERSION'],
                    'django-%s' % os.environ['DJANGO_VERSION'],
                    'CI'
                ]

            # Use Sauce connect
            username = os.environ['SAUCE_USERNAME']
            key = os.environ['SAUCE_ACCESS_KEY']
            hub_url = "%s:%s@localhost:4445" % (username, key)
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
        self.driver.get('%s%s' % (self.live_server_url, reverse('auth_login')))

        username_input = self.driver.find_element_by_name('username')
        username_input.send_keys("myuser")
        password_input = self.driver.find_element_by_name('password')
        password_input.send_keys("secret")
        self.driver.find_element_by_xpath('//input[@value="Login"]').click()

        # We should end up on login page as user was invalid
        # FIXME: This is currently broken with Sauce labs
        # http://support.saucelabs.com/entries/20629691
        #self.driver.find_element_by_name('username')


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


if DO_SELENIUM:
    classes = {}
    for platform in EXTRA_PLATFORMS:
        d = dict(SeleniumTests.__dict__)
        name = '%s_%s' % (
            SeleniumTests.__name__,
            platform
        )
        d.update({
            'caps': EXTRA_PLATFORMS[platform],
        })
        classes[name] = new.classobj(name, (SeleniumTests,), d)

    globals().update(classes)
