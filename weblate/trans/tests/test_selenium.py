#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


import math
import os
import time
from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
from unittest import SkipTest

import social_django.utils
from django.conf import settings
from django.core import mail
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import ElementNotVisibleException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.expected_conditions import (
    presence_of_element_located,
    staleness_of,
)
from selenium.webdriver.support.ui import Select, WebDriverWait

import weblate.screenshots.views
from weblate.fonts.tests.utils import FONT
from weblate.glossary.models import Glossary, Term
from weblate.lang.models import Language
from weblate.trans.models import Change, Component, Project, Unit
from weblate.trans.tests.test_models import BaseLiveServerTestCase
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.utils import (
    TempDirMixin,
    create_test_billing,
    create_test_user,
    get_test_file,
)
from weblate.vcs.ssh import get_key_data

TEST_BACKENDS = (
    "social_core.backends.email.EmailAuth",
    "social_core.backends.google.GoogleOAuth2",
    "social_core.backends.github.GithubOAuth2",
    "social_core.backends.bitbucket.BitbucketOAuth",
    "social_core.backends.suse.OpenSUSEOpenId",
    "social_core.backends.ubuntu.UbuntuOpenId",
    "social_core.backends.fedora.FedoraOpenId",
    "social_core.backends.facebook.FacebookOAuth2",
    "weblate.accounts.auth.WeblateUserBackend",
)

SOURCE_FONT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "static",
    "vendor",
    "font-source",
    "TTF",
    "SourceSansPro-Bold.ttf",
)


class SeleniumTests(BaseLiveServerTestCase, RegistrationTestMixin, TempDirMixin):
    driver = None
    driver_error = ""
    image_path = None
    site_domain = ""

    @classmethod
    def _databases_support_transactions(cls):
        # This is workaroud for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
            return False
        return super()._databases_support_transactions()

    @contextmanager
    def wait_for_page_load(self, timeout=30):
        old_page = self.driver.find_element_by_tag_name("html")
        yield
        WebDriverWait(self.driver, timeout).until(staleness_of(old_page))

    @classmethod
    def setUpClass(cls):
        # Screenshots storage
        cls.image_path = os.path.join(settings.BASE_DIR, "test-images")
        if not os.path.exists(cls.image_path):
            os.makedirs(cls.image_path)
        # Build Chrome driver
        options = Options()
        # Run headless
        options.headless = True
        # Seems to help in some corner cases, see
        # https://stackoverflow.com/a/50642913/225718
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # Need to revert fontconfig custom config for starting chrome
        backup = os.environ["FONTCONFIG_FILE"]
        del os.environ["FONTCONFIG_FILE"]

        try:
            cls.driver = webdriver.Chrome(options=options)
        except WebDriverException as error:
            cls.driver_error = str(error)
            if "CI_SELENIUM" in os.environ:
                raise

        # Restore custom fontconfig settings
        os.environ["FONTCONFIG_FILE"] = backup

        if cls.driver is not None:
            cls.driver.implicitly_wait(5)
            cls.actions = webdriver.ActionChains(cls.driver)

        super().setUpClass()

    def setUp(self):
        if self.driver is None:
            print("Selenium error: {}".format(self.driver_error))
            raise SkipTest("Webdriver not available: {}".format(self.driver_error))
        super().setUp()
        self.driver.get("{0}{1}".format(self.live_server_url, reverse("home")))
        self.driver.set_window_size(1200, 1024)
        self.site_domain = settings.SITE_DOMAIN
        settings.SITE_DOMAIN = "{}:{}".format(self.host, self.server_thread.port)

    def tearDown(self):
        super().tearDown()
        settings.SITE_DOMAIN = self.site_domain

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls.driver is not None:
            cls.driver.quit()
            cls.driver = None

    def scroll_top(self):
        self.driver.execute_script("window.scrollTo(0, 0)")

    def screenshot(self, name, scroll=True):
        """Captures named full page screenshot."""
        self.scroll_top()
        # Get window and document dimensions
        window_height = self.driver.execute_script("return window.innerHeight")
        scroll_height = self.driver.execute_script("return document.body.scrollHeight")
        scroll_width = self.driver.execute_script("return document.body.scrollWidth")
        # Calculate number of screnshots
        num = int(math.ceil(float(scroll_height) / float(window_height)))

        # Capture screenshots
        screenshots = []
        for i in range(num):
            if i > 0:
                self.driver.execute_script(
                    "window.scrollBy(%d,%d)" % (0, window_height)
                )
            screenshots.append(Image.open(BytesIO(self.driver.get_screenshot_as_png())))
            if not scroll:
                scroll_height = window_height
                break

        # Create final image
        stitched = Image.new("RGB", (scroll_width, scroll_height))

        # Stitch images together
        for i, img in enumerate(screenshots):
            offset = i * window_height

            # Remove overlapping area from last screenshot
            if i > 0 and i == num - 1:
                overlap_height = img.height - scroll_height % img.height
            else:
                overlap_height = 0

            stitched.paste(img, (0, offset - overlap_height))

        stitched.save(os.path.join(self.image_path, name))

        self.scroll_top()

    def click(self, element="", htmlid=None):
        """Wrapper to scroll into element for click."""
        if htmlid:
            element = self.driver.find_element_by_id(htmlid)
        if isinstance(element, str):
            element = self.driver.find_element_by_link_text(element)

        try:
            element.click()
        except ElementNotVisibleException:
            self.actions.move_to_element(element).perform()
            element.click()

    def clear_field(self, element):
        element.send_keys(Keys.CONTROL + "a")
        element.send_keys(Keys.DELETE)
        return element

    def do_login(self, create=True, superuser=False):
        # login page
        with self.wait_for_page_load():
            self.click(htmlid="login-button")

        # Create user
        if create:
            user = create_test_user()
            if superuser:
                user.is_superuser = True
                user.save()
            user.profile.language = "en"
            user.profile.save()
            user.profile.languages.set(
                Language.objects.filter(code__in=("he", "cs", "hu"))
            )
        else:
            user = None

        # Login
        username_input = self.driver.find_element_by_id("id_username")
        username_input.send_keys("weblate@example.org")
        password_input = self.driver.find_element_by_id("id_password")
        password_input.send_keys("testpassword")

        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_xpath('//input[@value="Sign in"]'))
        return user

    def open_manage(self, login=True):
        # Login as superuser
        if login:
            user = self.do_login(superuser=True)
        else:
            user = None

        # Open admin page
        with self.wait_for_page_load():
            self.click(htmlid="admin-button")
        return user

    def open_admin(self, login=True):
        user = self.open_manage(login)
        with self.wait_for_page_load():
            self.click("Tools")
        with self.wait_for_page_load():
            self.click("Django admin interface")
        return user

    def test_failed_login(self):
        self.do_login(create=False)

        # We should end up on login page as user was invalid
        self.driver.find_element_by_id("id_username")

    def test_login(self):
        # Do proper login with new user
        self.do_login()

        # Load profile
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="settings-button")

        # Wait for profile to load
        self.driver.find_element_by_id("notifications")

        # Load translation memory
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="memory-button")

        self.screenshot("memory.png")

        # Finally logout
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="logout-button")

        # We should be back on home page
        self.driver.find_element_by_id("browse-projects")

    def register_user(self):
        # registration page
        with self.wait_for_page_load():
            self.click(htmlid="register-button")

        # Fill in registration form
        self.driver.find_element_by_id("id_email").send_keys("weblate@example.org")
        self.driver.find_element_by_id("id_username").send_keys("test-example")
        self.driver.find_element_by_id("id_fullname").send_keys("Test Example")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_xpath('//input[@value="Register"]'))

        # Wait for registration email
        loops = 0
        while not mail.outbox:
            time.sleep(1)
            loops += 1
            if loops > 20:
                break

        return self.assert_registration_mailbox()

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
                print("Ignoring: {0}".format(error))

        # Confirm account
        self.driver.get(url)

        # Check we got message
        self.assertTrue(
            "You have activated" in self.driver.find_element_by_tag_name("body").text
        )

        # Check we're signed in
        self.click(htmlid="user-dropdown")
        self.assertTrue(
            "Test Example" in self.driver.find_element_by_id("profile-name").text
        )

    def test_register_nocookie(self):
        """Test registration without cookies."""
        self.test_register(True)

    @override_settings(WEBLATE_GPG_IDENTITY="Weblate <weblate@example.com>")
    def test_gpg(self):
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_partial_link_text("About Weblate"))
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_partial_link_text("Keys"))
        self.screenshot("about-gpg.png")

    def test_ssh(self):
        """Test SSH admin interface."""
        self.open_admin()

        time.sleep(0.5)
        self.screenshot("admin.png")

        # Open SSH page
        with self.wait_for_page_load():
            self.click("SSH keys")

        # Generate SSH key
        if get_key_data() is None:
            with self.wait_for_page_load():
                self.click(htmlid="generate-ssh-button")

        # Add SSH host key
        self.driver.find_element_by_id("id_host").send_keys("github.com")
        with self.wait_for_page_load():
            self.click(htmlid="ssh-add-button")

        self.screenshot("ssh-keys-added.png")

        # Open SSH page for final screenshot
        with self.wait_for_page_load():
            self.click("SSH keys")
        self.screenshot("ssh-keys.png")

    def create_component(self):
        project = Project.objects.create(name="WeblateOrg", slug="weblateorg")
        Component.objects.create(
            name="Language names",
            slug="language-names",
            project=project,
            repo="https://github.com/WeblateOrg/demo.git",
            filemask="weblate/langdata/locale/*/LC_MESSAGES/django.po",
            new_base="weblate/langdata/locale/django.pot",
            file_format="po",
        )
        Component.objects.create(
            name="Django",
            slug="django",
            project=project,
            repo="weblate://weblateorg/language-names",
            filemask="weblate/locale/*/LC_MESSAGES/django.po",
            new_base="weblate/locale/django.pot",
            file_format="po",
        )
        return project

    def view_site(self):
        with self.wait_for_page_load():
            self.click(htmlid="return-to-weblate")

    def test_dashboard(self):
        self.do_login()
        # Generate nice changes data
        for day in range(365):
            for _unused in range(int(10 + 10 * math.sin(2 * math.pi * day / 30))):
                change = Change.objects.create(action=Change.ACTION_CREATE_PROJECT)
                change.timestamp -= timedelta(days=day)
                change.save()

        # Render activity
        self.click("Insights")
        self.click("Activity")
        time.sleep(0.5)
        self.screenshot("activity.png")

        # Screenshot search
        self.click("Search")
        self.screenshot("search.png")

    @override_settings(AUTHENTICATION_BACKENDS=TEST_BACKENDS)
    def test_auth_backends(self):
        try:
            # psa creates copy of settings...
            orig_backends = social_django.utils.BACKENDS
            social_django.utils.BACKENDS = TEST_BACKENDS
            user = self.do_login()
            user.social_auth.create(provider="google-oauth2", uid=user.email)
            user.social_auth.create(provider="github", uid="123456")
            user.social_auth.create(provider="bitbucket", uid="weblate")
            self.click(htmlid="user-dropdown")
            with self.wait_for_page_load():
                self.click(htmlid="settings-button")
            self.click("Account")
            self.screenshot("authentication.png")
        finally:
            social_django.utils.BACKENDS = orig_backends

    def test_screenshots(self):
        """Screenshot tests."""
        text = (
            "Automatic translation via machine translation uses active "
            "machine translation engines to get the best possible "
            "translations and applies them in this project."
        )
        self.create_component()
        language = Language.objects.get(code="cs")

        source = Unit.objects.get(
            source=text, translation__language=language
        ).source_info
        source.explanation = "Help text for automatic translation tool"
        source.save()
        glossary = Glossary.objects.get()
        Term.objects.create(
            user=None,
            glossary=glossary,
            language=language,
            source="machine translation",
            target="strojový překlad",
        )
        Term.objects.create(
            user=None,
            glossary=glossary,
            language=language,
            source="project",
            target="projekt",
        )
        source.translation.component.alert_set.all().delete()

        def capture_unit(name, tab):
            unit = Unit.objects.get(source=text, translation__language=language)
            with self.wait_for_page_load():
                self.driver.get(
                    "{0}{1}".format(self.live_server_url, unit.get_absolute_url())
                )
            self.click(htmlid=tab)
            self.screenshot(name)
            with self.wait_for_page_load():
                self.click("Dashboard")

        def wait_search():
            WebDriverWait(self.driver, 30).until(
                presence_of_element_located(
                    (By.XPATH, '//tbody[@id="search-results"]/tr')
                )
            )

        self.do_login(superuser=True)
        capture_unit("source-information.png", "toggle-nearby")
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        with self.wait_for_page_load():
            self.click("Django")
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Screenshots")

        # Upload screenshot
        self.driver.find_element_by_id("id_name").send_keys("Automatic translation")
        element = self.driver.find_element_by_id("id_image")
        element.send_keys(
            element._upload(get_test_file("screenshot.png"))  # noqa: SLF001
        )
        with self.wait_for_page_load():
            element.submit()

        # Perform OCR
        if weblate.screenshots.views.HAS_OCR:
            self.click(htmlid="screenshots-auto")
            wait_search()

            self.screenshot("screenshot-ocr.png")

        # Add string manually
        self.driver.find_element_by_id("search-input").send_keys("'{}'".format(text))
        self.click(htmlid="screenshots-search")
        wait_search()
        self.click(self.driver.find_element_by_class_name("add-string"))

        # Unit should have screenshot assigned now
        capture_unit("screenshot-context.png", "toggle-machinery")

    def test_admin(self):
        """Test admin interface."""
        self.do_login(superuser=True)
        self.screenshot("admin-wrench.png")
        self.create_component()
        # Open admin page
        self.open_admin(login=False)

        # Component list
        with self.wait_for_page_load():
            self.click("Component lists")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("addlink"))
        element = self.driver.find_element_by_id("id_name")
        element.send_keys("All components")
        self.click("Add another Automatic component list assignment")
        self.clear_field(
            self.driver.find_element_by_id("id_autocomponentlist_set-0-project_match")
        ).send_keys("^.*$")
        self.clear_field(
            self.driver.find_element_by_id("id_autocomponentlist_set-0-component_match")
        ).send_keys("^.*$")
        self.screenshot("componentlist-add.png")
        with self.wait_for_page_load():
            element.submit()

        # Ensure the component list is there
        with self.wait_for_page_load():
            self.click("All components")

        # Announcement
        with self.wait_for_page_load():
            self.click("Weblate translations")
        with self.wait_for_page_load():
            self.click("Announcements")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("addlink"))
        Select(self.driver.find_element_by_id("id_project")).select_by_visible_text(
            "WeblateOrg"
        )
        element = self.driver.find_element_by_id("id_message")
        element.send_keys("Translations will be used only if they reach 60%.")
        self.screenshot("announcement.png")
        with self.wait_for_page_load():
            element.submit()
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("addlink"))
        Select(self.driver.find_element_by_id("id_language")).select_by_visible_text(
            "Czech"
        )
        element = self.driver.find_element_by_id("id_message")
        element.send_keys("Czech translators rock!")
        with self.wait_for_page_load():
            element.submit()

        # Announcement display
        self.view_site()
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Manage")
        self.click("Post announcement")
        self.screenshot("announcement-project.png")

        with self.wait_for_page_load():
            self.click("Dashboard")
        self.click(htmlid="languages-menu")
        with self.wait_for_page_load():
            self.click("Browse all languages")
        with self.wait_for_page_load():
            self.click("Czech")
        self.screenshot("announcement-language.png")

    def test_weblate(self):
        user = self.open_admin()
        language_regex = "^(cs|he|hu)$"

        # Add project
        with self.wait_for_page_load():
            self.click("Projects")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("addlink"))
        self.driver.find_element_by_id("id_name").send_keys("WeblateOrg")
        Select(self.driver.find_element_by_id("id_access_control")).select_by_value("1")
        self.driver.find_element_by_id("id_web").send_keys("https://weblate.org/")
        self.driver.find_element_by_id("id_mail").send_keys("weblate@lists.cihar.com")
        self.driver.find_element_by_id("id_instructions").send_keys(
            "https://weblate.org/contribute/"
        )
        self.screenshot("add-project.png")
        with self.wait_for_page_load():
            self.driver.find_element_by_id("id_name").submit()

        # Add bilingual component
        with self.wait_for_page_load():
            self.click("Home")
        with self.wait_for_page_load():
            self.click("Components")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("addlink"))

        self.driver.find_element_by_id("id_name").send_keys("Language names")
        Select(self.driver.find_element_by_id("id_project")).select_by_visible_text(
            "WeblateOrg"
        )
        self.driver.find_element_by_id("id_repo").send_keys(
            "https://github.com/WeblateOrg/demo.git"
        )
        self.driver.find_element_by_id("id_repoweb").send_keys(
            "https://github.com/WeblateOrg/demo/blob/"
            "{{branch}}/{{filename}}#L{{line}}"
        )
        self.driver.find_element_by_id("id_filemask").send_keys(
            "weblate/langdata/locale/*/LC_MESSAGES/django.po"
        )
        self.driver.find_element_by_id("id_new_base").send_keys(
            "weblate/langdata/locale/django.pot"
        )
        Select(self.driver.find_element_by_id("id_file_format")).select_by_value("po")
        Select(self.driver.find_element_by_id("id_license")).select_by_value(
            "GPL-3.0-or-later"
        )
        self.clear_field(self.driver.find_element_by_id("id_language_regex")).send_keys(
            language_regex
        )
        self.screenshot("add-component.png")
        # This takes long
        with self.wait_for_page_load(timeout=1200):
            self.driver.find_element_by_id("id_name").submit()
        with self.wait_for_page_load():
            self.click("Language names")

        # Add monolingual component
        with self.wait_for_page_load():
            self.click("Components")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("addlink"))
        self.driver.find_element_by_id("id_name").send_keys("Android")
        Select(self.driver.find_element_by_id("id_project")).select_by_visible_text(
            "WeblateOrg"
        )
        self.driver.find_element_by_id("id_repo").send_keys(
            "weblate://weblateorg/language-names"
        )
        self.driver.find_element_by_id("id_filemask").send_keys(
            "app/src/main/res/values-*/strings.xml"
        )
        self.driver.find_element_by_id("id_template").send_keys(
            "app/src/main/res/values/strings.xml"
        )
        Select(self.driver.find_element_by_id("id_file_format")).select_by_value(
            "aresource"
        )
        Select(self.driver.find_element_by_id("id_license")).select_by_value("MIT")
        self.screenshot("add-component-mono.png")
        # This takes long
        with self.wait_for_page_load(timeout=1200):
            self.driver.find_element_by_id("id_name").submit()
        with self.wait_for_page_load():
            self.click("Android")

        # Load Weblate project page
        self.view_site()
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")

        self.screenshot("project-overview.png")

        # User management
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Users")
        element = self.driver.find_element_by_id("id_user")
        element.send_keys("testuser")
        with self.wait_for_page_load():
            element.submit()
        with self.wait_for_page_load():
            self.click("Manage users")
        self.screenshot("manage-users.png")
        # Access control setings
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Settings")
        self.click("Access")
        self.screenshot("project-access.png")
        self.click("Workflow")
        self.screenshot("project-workflow.png")
        # The project is now watched
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("WeblateOrg")

        # Engage page
        self.click("Share")
        with self.wait_for_page_load():
            self.click("Status widgets")
        self.screenshot("promote.png")
        with self.wait_for_page_load():
            self.click(htmlid="engage-link")
        self.screenshot("engage.png")
        with self.wait_for_page_load():
            self.click(htmlid="engage-project")

        # Glossary
        with self.wait_for_page_load():
            self.click("Glossaries")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_partial_link_text("Czech"))
        self.click("Add new word")
        self.driver.find_element_by_id("id_source").send_keys("language")
        element = self.driver.find_element_by_id("id_target")
        element.send_keys("jazyk")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("glossary-edit.png")
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        with self.wait_for_page_load():
            self.click("Glossaries")
        self.screenshot("project-glossaries.png")
        with self.wait_for_page_load():
            self.click("WeblateOrg")

        # Addons
        self.click("Components")
        with self.wait_for_page_load():
            self.click("Language names")
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Addons")
        self.screenshot("addons.png")
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_xpath(
                    '//button[@data-addon="weblate.discovery.discovery"]'
                )
            )
        element = self.driver.find_element_by_id("id_match")
        element.send_keys(
            "weblate/locale/(?P<language>[^/]*)/LC_MESSAGES/"
            "(?P<component>[^/]*)\\.po"
        )
        self.clear_field(self.driver.find_element_by_id("id_language_regex")).send_keys(
            language_regex
        )
        self.driver.find_element_by_id("id_new_base_template").send_keys(
            "weblate/locale/{{ component }}.pot"
        )
        self.clear_field(self.driver.find_element_by_id("id_name_template")).send_keys(
            "{{ component|title }}"
        )
        Select(self.driver.find_element_by_id("id_file_format")).select_by_value("po")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("addon-discovery.png")
        element = self.driver.find_element_by_id("id_confirm")
        self.click(element)
        # This takes long
        with self.wait_for_page_load(timeout=1200):
            element.submit()
        with self.wait_for_page_load():
            self.click("Language names")

        # Reports
        self.click("Insights")
        self.click("Translation reports")
        self.click("Insights")
        self.screenshot("reporting.png")

        # Contributor agreeement
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Settings")
        element = self.driver.find_element_by_id("id_agreement")
        element.send_keys("This is an agreement.")
        with self.wait_for_page_load():
            element.submit()
        with self.wait_for_page_load():
            self.click("Language names")
        self.screenshot("contributor-agreement.png")
        with self.wait_for_page_load():
            self.click("View contributor agreement")
        element = self.driver.find_element_by_id("id_confirm")
        self.click(element)
        with self.wait_for_page_load():
            element.submit()

        # Translation page
        with self.wait_for_page_load():
            self.click("Czech")
        with self.wait_for_page_load():
            self.click("Django")
        self.screenshot("strings-to-check.png")
        self.click("Files")
        self.click("Upload translation")
        self.click("Files")
        self.screenshot("export-import.png")
        self.click("Tools")
        self.click("Automatic translation")
        self.click(htmlid="id_select_auto_source_2")
        self.click("Tools")
        self.screenshot("automatic-translation.png")
        self.click("Search")
        element = self.driver.find_element_by_id("id_q")
        element.send_keys("'%(count)s word'")
        with self.wait_for_page_load():
            element.submit()
        self.click("History")
        self.screenshot("format-highlight.png")
        self.click("Comments")
        self.screenshot("plurals.png")

        # Test search dropdown
        dropdown = self.driver.find_element_by_id("query-dropdown")
        dropdown.click()
        time.sleep(0.5)
        self.screenshot("query-dropdown.png")
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element_by_partial_link_text("Not translated strings")
            )
        self.driver.find_element_by_id("id_34a4642999e44a2b_0")

        # Test sort dropdown
        sort = self.driver.find_element_by_id("query-sort-dropdown")
        sort.click()
        time.sleep(0.5)
        self.screenshot("query-sort.png")
        with self.wait_for_page_load():
            self.click("Position")

        # Return to original unit
        element = self.driver.find_element_by_id("id_q")
        self.clear_field(element)
        element.send_keys("'%(count)s word'")
        with self.wait_for_page_load():
            element.submit()

        # Trigger check
        self.clear_field(self.driver.find_element_by_id("id_a2a808c8ccbece08_0"))
        element = self.driver.find_element_by_id("id_a2a808c8ccbece08_1")
        self.clear_field(element)
        element.send_keys("několik slov")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("checks.png")

        # Secondary language display
        user.profile.secondary_languages.set(Language.objects.filter(code__in=("he",)))
        with self.wait_for_page_load():
            self.click("Czech")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_partial_link_text("All strings"))
        self.click("Other languages")
        self.screenshot("secondary-language.png")

        # RTL translation
        with self.wait_for_page_load():
            self.click("Django")
        with self.wait_for_page_load():
            self.click("Hebrew")
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_partial_link_text("All strings"))
        self.screenshot("visual-keyboard.png")

        # Profile
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="settings-button")
        self.click("Preferences")
        self.screenshot("dashboard-dropdown.png")
        self.click("Notifications")
        self.screenshot("profile-subscriptions.png")
        self.click("Licenses")
        self.screenshot("profile-licenses.png")

        # Dashboard
        with self.wait_for_page_load():
            self.click("Dashboard")
        self.screenshot("your-translations.png")

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_add_component(self):
        """Test user adding project and component."""
        user = self.do_login()
        create_test_billing(user)

        # Open billing page
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="billing-button")
        self.screenshot("user-billing.png")

        # Click on add project
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("billing-add-project"))

        # Add project
        self.driver.find_element_by_id("id_name").send_keys("WeblateOrg")
        self.driver.find_element_by_id("id_web").send_keys("https://weblate.org/")
        self.driver.find_element_by_id("id_mail").send_keys("weblate@lists.cihar.com")
        self.driver.find_element_by_id("id_instructions").send_keys(
            "https://weblate.org/contribute/"
        )
        self.screenshot("user-add-project.png")
        with self.wait_for_page_load():
            self.driver.find_element_by_id("id_name").submit()
        self.screenshot("user-add-project-done.png")

        # Click on add component
        with self.wait_for_page_load():
            self.click(self.driver.find_element_by_class_name("project-add-component"))

        # Add component
        self.driver.find_element_by_id("id_name").send_keys("Language names")
        self.driver.find_element_by_id("id_repo").send_keys(
            "https://github.com/WeblateOrg/demo.git"
        )
        self.screenshot("user-add-component-init.png")
        with self.wait_for_page_load(timeout=1200):
            self.driver.find_element_by_id("id_name").submit()

        self.screenshot("user-add-component-discovery.png")
        self.driver.find_element_by_id("id_id_discovery_0_1").click()
        with self.wait_for_page_load(timeout=1200):
            self.driver.find_element_by_id("id_name").submit()

        self.driver.find_element_by_id("id_repoweb").send_keys(
            "https://github.com/WeblateOrg/demo/blob/"
            "{{branch}}/{{filename}}#L{{line}}"
        )
        self.driver.find_element_by_id("id_filemask").send_keys(
            "weblate/langdata/locale/*/LC_MESSAGES/django.po"
        )
        self.driver.find_element_by_id("id_new_base").send_keys(
            "weblate/langdata/locale/django.pot"
        )
        Select(self.driver.find_element_by_id("id_file_format")).select_by_value("po")
        Select(self.driver.find_element_by_id("id_license")).select_by_value(
            "GPL-3.0-or-later"
        )
        self.clear_field(self.driver.find_element_by_id("id_language_regex")).send_keys(
            "^(cs|he|hu)$"
        )
        self.screenshot("user-add-component.png")

    def test_alerts(self):
        project = Project.objects.create(name="WeblateOrg", slug="weblateorg")
        Component.objects.create(
            name="Duplicates",
            slug="duplicates",
            project=project,
            repo="https://github.com/WeblateOrg/test.git",
            filemask="po-duplicates/*.dpo",
            new_base="po-duplicates/hello.pot",
            file_format="po",
        )
        self.do_login(superuser=True)
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        with self.wait_for_page_load():
            self.click("Duplicates")
        self.click("Alerts")
        self.screenshot("alerts.png")

        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Community localization checklist")
        self.screenshot("guide.png")

    def test_fonts(self):
        self.create_component()
        self.do_login(superuser=True)
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Fonts")

        self.click(htmlid="tab_fonts")

        # Upload font
        element = self.driver.find_element_by_id("id_font")
        element.send_keys(element._upload(FONT))  # noqa: SF01,SLF001
        with self.wait_for_page_load():
            self.click(htmlid="upload_font_submit")

        self.screenshot("font-edit.png")

        with self.wait_for_page_load():
            self.click("Fonts")

        # Upload second font
        element = self.driver.find_element_by_id("id_font")
        element.send_keys(element._upload(SOURCE_FONT))  # noqa: SF01,SLF001
        with self.wait_for_page_load():
            self.click(htmlid="upload_font_submit")

        with self.wait_for_page_load():
            self.click("Fonts")

        self.screenshot("font-list.png")

        self.click(htmlid="tab_groups")

        # Create group
        Select(self.driver.find_element_by_id("id_group_font")).select_by_visible_text(
            "Source Sans Pro Bold"
        )
        element = self.driver.find_element_by_id("id_group_name")
        element.send_keys("default-font")
        with self.wait_for_page_load():
            element.submit()

        Select(self.driver.find_element_by_id("id_font")).select_by_visible_text(
            "Droid Sans Fallback Regular"
        )
        element = self.driver.find_element_by_id("id_language")
        Select(element).select_by_visible_text("Japanese")
        with self.wait_for_page_load():
            element.submit()
        Select(self.driver.find_element_by_id("id_font")).select_by_visible_text(
            "Droid Sans Fallback Regular"
        )
        element = self.driver.find_element_by_id("id_language")
        Select(element).select_by_visible_text("Korean")
        with self.wait_for_page_load():
            element.submit()

        self.screenshot("font-group-edit.png")

        with self.wait_for_page_load():
            self.click("Font groups")

        self.screenshot("font-group-list.png")

    def test_backup(self):
        self.create_temp()
        try:
            self.open_manage()
            self.screenshot("support.png")
            with self.wait_for_page_load():
                self.click("Backups")
            element = self.driver.find_element_by_id("id_repository")
            element.send_keys(self.tempdir)
            with self.wait_for_page_load():
                element.submit()
            with self.wait_for_page_load():
                self.click(self.driver.find_element_by_class_name("runbackup"))
            self.click(self.driver.find_element_by_class_name("createdbackup"))
            time.sleep(0.5)
            self.screenshot("backups.png")
        finally:
            self.remove_temp()

    def test_explanation(self):
        project = self.create_component()
        Component.objects.create(
            name="Android",
            slug="android",
            project=project,
            repo="weblate://weblateorg/language-names",
            filemask="app/src/main/res/values-*/strings.xml",
            template="app/src/main/res/values/strings.xml",
            file_format="aresource",
        )

        self.do_login(superuser=True)
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Labels")
        element = self.driver.find_element_by_id("id_name")
        element.send_keys("Current sprint")
        self.click(self.driver.find_element_by_class_name("label-green"))
        with self.wait_for_page_load():
            element.submit()
        element = self.driver.find_element_by_id("id_name")
        element.send_keys("Next sprint")
        self.click(self.driver.find_element_by_class_name("label-aqua"))
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("labels.png")

        # Navigate to component
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        with self.wait_for_page_load():
            self.click("Android")

        # Edit variant configuration
        self.click("Manage")
        with self.wait_for_page_load():
            self.click("Settings")
        self.click("Translation")
        element = self.driver.find_element_by_id("id_variant_regex")
        element.send_keys("_(short|min)$")
        self.screenshot("variants-settings.png")
        with self.wait_for_page_load():
            element.submit()

        # Navigate to the source language
        with self.wait_for_page_load():
            self.click("Android")
        with self.wait_for_page_load():
            self.click("English")
        self.screenshot("source-review.png")

        # Find string with variants
        self.click("Search")
        element = self.driver.find_element_by_id("id_q")
        element.send_keys("Monday")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("source-review-detail.png")

        # Display variants
        self.click(htmlid="toggle-variants")
        self.screenshot("variants-translate.png")

        # Edit context
        self.click(htmlid="edit-context")
        time.sleep(0.5)
        self.screenshot("source-review-edit.png", scroll=False)

        # Close modal dialog
        self.driver.find_element_by_id("id_extra_flags").send_keys(Keys.ESCAPE)
        time.sleep(0.5)
