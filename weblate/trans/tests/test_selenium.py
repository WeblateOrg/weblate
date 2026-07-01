# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import math
import os
import time
import warnings
from contextlib import contextmanager, suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Literal, cast, overload
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.files import File
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpRequest
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotVisibleException,
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.expected_conditions import (
    element_to_be_clickable,
    presence_of_element_located,
    staleness_of,
)
from selenium.webdriver.support.ui import Select, WebDriverWait

from weblate.auth.models import AutoGroup, Group, Role, User
from weblate.configuration.models import Setting, SettingCategory
from weblate.fonts.tests.utils import FONT, FONT_SOURCE
from weblate.gitexport.models import get_export_url
from weblate.lang.models import Language
from weblate.machinery.base import MACHINERY_DEFAULT_THRESHOLD
from weblate.machinery.dummy import DummyTranslation
from weblate.metrics.models import Metric
from weblate.metrics.wrapper import MetricsWrapper
from weblate.screenshots.models import Screenshot
from weblate.screenshots.views import ensure_tesseract_language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Announcement,
    Change,
    Component,
    ComponentList,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.trans.tests.test_models import BaseLiveServerTestCase
from weblate.trans.tests.test_views import RegistrationTestMixin
from weblate.trans.tests.utils import (
    TempDirMixin,
    create_another_user,
    create_test_billing,
    create_test_user,
    get_test_file,
    social_core_override_settings,
)
from weblate.utils.data import data_dir
from weblate.utils.files import remove_tree
from weblate.utils.stats import GlobalStats, ProjectLanguage
from weblate.vcs.ssh import ssh_file
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Iterator

    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement

    from weblate.machinery.types import DownloadTranslations
    from weblate.utils.stats import BaseStats


class SeleniumDummyTranslation(DummyTranslation):
    """Dummy machine translation for Selenium hotkey tests."""

    name = "Selenium Dummy"

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadTranslations:
        _ = (source_language, target_language, unit, user, threshold)
        yield {
            "text": "initial machinery 1",
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
        yield {
            "text": "initial machinery 2",
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }


TEST_BACKENDS = (
    "social_core.backends.email.EmailAuth",
    "social_core.backends.google.GoogleOAuth2",
    "social_core.backends.github.GithubOAuth2",
    "social_core.backends.bitbucket.BitbucketOAuth2",
    "social_core.backends.suse.OpenSUSEOpenId",
    "social_core.backends.ubuntu.UbuntuOpenId",
    "social_core.backends.fedora.FedoraOpenId",
    "social_core.backends.facebook.FacebookOAuth2",
    "weblate.accounts.auth.WeblateUserBackend",
)

SCREENSHOT_SITE_DOMAIN = "weblate.example.com"
SCREENSHOT_DATE = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
SELENIUM_GPG_KEY_ID = "B17C8337FA04DF8D4D3569AF882B2A22730AAF03"
SELENIUM_SSH_KEY_FIXTURES = (
    ("id_rsa.pub", "selenium-keys/id_rsa.pub"),
    ("id_ed25519.pub", "selenium-keys/id_ed25519.pub"),
)
PERFORMANCE_REPORT_DISK_USAGE = SimpleNamespace(
    total=1024 * 1024 * 1024 * 1024,
    used=400 * 1024 * 1024 * 1024,
    free=624 * 1024 * 1024 * 1024,
)
PERFORMANCE_REPORT_HEADERS = {
    "Host": SCREENSHOT_SITE_DOMAIN,
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Selenium screenshot browser",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": f"http://{SCREENSHOT_SITE_DOMAIN}/",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en,en-US;q=0.9",
}


# The fixture repositories are known public GitHub repos; allowlisting them
# avoids flaky runtime DNS checks while keeping the real import path covered.
@override_settings(STATS_LAZY=False, VCS_ALLOW_HOSTS={"github.com"})
class SeleniumTests(BaseLiveServerTestCase, RegistrationTestMixin, TempDirMixin):
    _driver: WebDriver | None = None
    _driver_error: str = ""
    image_path = os.path.join(settings.BASE_DIR, "test-images")
    site_domain = ""

    @contextmanager
    def wait_for_page_load(self, timeout: int = 30) -> Iterator[None]:
        old_page = self.driver.find_element(By.TAG_NAME, "html")
        success = False
        try:
            yield
            success = True
        finally:
            if success:
                try:
                    WebDriverWait(self.driver, timeout).until(staleness_of(old_page))
                except WebDriverException:
                    # Retry the same condition to workaround issue in
                    # Chromedriver/Selenium, see
                    # https://github.com/SeleniumHQ/selenium/issues/15401
                    time.sleep(0.1)
                    WebDriverWait(self.driver, timeout).until(staleness_of(old_page))
                WebDriverWait(self.driver, timeout).until(self.is_page_loaded)

    @staticmethod
    def is_page_loaded(driver: WebDriver) -> bool:
        try:
            return bool(
                driver.execute_script(
                    """
                    if (document.readyState !== "complete") {
                        return false;
                    }
                    if (!document.querySelector('meta[name="argon2id-worker-url"]')) {
                        return true;
                    }
                    const status = {
                        slugify: typeof window.slugify !== "undefined",
                        DateRangePicker: typeof window.DateRangePicker !== "undefined",
                        getNumber: typeof window.getNumber === "function",
                        quoteSearch: typeof window.quoteSearch === "function",
                        compareCells: typeof window.compareCells === "function",
                    };
                    return Object.values(status).every(Boolean);
                    """
                )
            )
        except WebDriverException:
            return False

    @classmethod
    def setUpClass(cls) -> None:
        # Screenshots storage
        if not os.path.exists(cls.image_path):
            os.makedirs(cls.image_path)
        # Build Chrome driver
        options = Options()
        # Run headless
        options.add_argument("--headless=new")
        # Seems to help in some corner cases, see
        # https://stackoverflow.com/a/50642913/225718
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        # Force Chrome in English
        options.add_argument("--lang=en")
        # Accept English as primary language, this does not seem to work
        options.add_experimental_option("prefs", {"intl.accept_languages": "en,en_US"})

        # Need to revert fontconfig custom config for starting chrome
        backup_fc = os.environ.get("FONTCONFIG_FILE")
        if backup_fc is not None:
            del os.environ["FONTCONFIG_FILE"]

        # Force English locales, the --lang and accept_language settings does not
        # work in some cases
        backup_lang = os.environ.get("LANG")
        os.environ["LANG"] = "en_US.UTF-8"

        try:
            cls._driver = webdriver.Chrome(options=options)
        except WebDriverException as error:
            cls._driver_error = str(error)
            if "CI_SELENIUM" in os.environ:
                raise
        else:
            # Increase webdriver timeout to avoid occasional errors in CI
            cls._driver.command_executor.client_config.timeout = 300
            cls._driver.execute_cdp_cmd(
                "Network.setCacheDisabled", {"cacheDisabled": True}
            )
            cls._driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            # Track in-flight fetch() requests so screenshots can wait for AJAX
            cls._driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                    (() => {
                        window.__weblateActiveFetches = 0;
                        const original = window.fetch;
                        if (typeof original !== "function" || original.__weblateWrapped) {
                            return;
                        }
                        const wrapped = (...args) => {
                            window.__weblateActiveFetches += 1;
                            return original.apply(window, args).finally(() => {
                                window.__weblateActiveFetches -= 1;
                            });
                        };
                        wrapped.__weblateWrapped = true;
                        window.fetch = wrapped;
                    })();
                    """
                },
            )

        # Restore custom fontconfig settings
        if backup_fc is not None:
            os.environ["FONTCONFIG_FILE"] = backup_fc
        # Restore locales
        if backup_lang is None:
            del os.environ["LANG"]
        else:
            os.environ["LANG"] = backup_lang

        if cls._driver is not None:
            cls._driver.implicitly_wait(5)

        # Configure verbose logging to be shown in case of the test failure
        logger = logging.getLogger("selenium")
        logger.setLevel(logging.DEBUG)

        super().setUpClass()

    @cached_property
    def actions(self) -> webdriver.ActionChains:
        return webdriver.ActionChains(self.driver)

    @property
    def driver(self) -> WebDriver:
        if self._driver is None:
            warnings.warn(f"Selenium error: {self._driver_error}", stacklevel=1)
            self.skipTest(f"Webdriver not available: {self._driver_error}")
        return self._driver

    def setUp(self) -> None:
        super().setUp()
        self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
        self.driver.set_window_size(1200, 1024)
        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{reverse('home')}")
        self.site_domain = settings.SITE_DOMAIN
        settings.SITE_DOMAIN = f"{self.host}:{self.server_thread.port}"

    def tearDown(self) -> None:
        super().tearDown()
        settings.SITE_DOMAIN = self.site_domain

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        if cls._driver is not None:
            cls._driver.quit()
            cls._driver = None

    def scroll_top(self) -> None:
        self.driver.execute_script("window.scrollTo(0, 0)")

    def assert_text_contains(self, css_selector: str, text: str) -> None:
        """Assert the element matching css_selector contains text."""
        self.assertIn(
            text,
            self.driver.find_element(By.CSS_SELECTOR, css_selector).text,
        )

    def install_selenium_ssh_keys(self) -> None:
        """Install deterministic display-only SSH keys for screenshots."""
        for filename, fixture in SELENIUM_SSH_KEY_FIXTURES:
            path = ssh_file(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                Path(get_test_file(fixture)).read_text(encoding="utf-8"),
                encoding="utf-8",
            )

    def clear_project_stats_cache(self, project: Project) -> None:
        """Drop stats cache entries that can survive the flushed test database."""
        translations = list(
            Translation.objects.filter(component__project=project).select_related(
                "language"
            )
        )
        stats = [
            project.stats,
            *(component.stats for component in project.component_set.all()),
            *(translation.stats for translation in translations),
            *(
                ProjectLanguage(project, language).stats
                for language in {translation.language for translation in translations}
            ),
        ]
        cache.delete_many({stat.cache_key for stat in stats})

    def clear_weblateorg_fixture_path(self) -> None:
        """Drop VCS state left by earlier flushed Selenium tests."""
        remove_tree(os.path.join(data_dir("vcs"), "weblateorg"), ignore_errors=True)

    def populate_global_activity_metrics(self) -> None:
        """Create deterministic metric rows for the generated activity history."""
        today = timezone.now().date()
        scope = Metric.SCOPE_GLOBAL
        relation = 0
        cache.delete(GlobalStats().cache_key)
        Metric.objects.filter_metric(scope, relation).delete()

        wrapper = MetricsWrapper(None, scope, relation)
        cache_keys = []
        activity_months = []
        last_month_date = today.replace(day=1) - timedelta(days=1)
        month = last_month_date.month
        year = last_month_date.year
        for _unused in range(12):
            activity_months.append((year, month))
            cache_keys.extend(
                (
                    wrapper.get_month_cache_key(year, month),
                    wrapper.get_month_cache_key(year - 1, month),
                )
            )
            month -= 1
            if month < 1:
                month = 12
                year -= 1
        cache.delete_many(cache_keys)

        Metric.objects.bulk_create(
            [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=0,
                    date=date(year, month, 15),
                    changes=18 + position * 6,
                )
                for position, (year, month) in enumerate(reversed(activity_months))
            ]
            + [
                Metric(
                    scope=scope,
                    relation=relation,
                    secondary=0,
                    date=date(year - 1, month, 15),
                    changes=8 + position * 3,
                )
                for position, (year, month) in enumerate(reversed(activity_months))
            ]
        )
        Metric.objects.collect_global()

    def count_elements(self, css_selector: str) -> int:
        """Return the count of elements matching css_selector on the current page."""
        return len(self.driver.find_elements(By.CSS_SELECTOR, css_selector))

    def assert_labeled_control(self, htmlid: str, label_text: str) -> None:
        """Assert a form control has a visible label associated by ID."""
        self.driver.find_element(By.ID, htmlid)
        labels = self.driver.find_elements(By.CSS_SELECTOR, f'label[for="{htmlid}"]')
        self.assertTrue(labels, f"Missing label for #{htmlid}")
        self.assertTrue(
            any(label_text in label.text for label in labels),
            f"Missing label text {label_text!r} for #{htmlid}",
        )

    def wait_for_ajax_tab(
        self, tab_target: str, expected_text: str, timeout: int = 30
    ) -> None:
        """Wait for AJAX-loaded tab content to be rendered."""
        WebDriverWait(self.driver, timeout).until(
            lambda driver: driver.execute_script(
                """
                const tabTarget = arguments[0];
                const expectedText = arguments[1];
                const tab = Array.from(
                    document.querySelectorAll(
                        '[data-bs-toggle="tab"][data-bs-target]',
                    ),
                ).find(
                    (element) =>
                        element.getAttribute("data-bs-target") === tabTarget,
                );
                const content = document.querySelector(tabTarget);
                if (!tab || !content) {
                    return false;
                }
                const text = content.textContent || "";
                return Boolean(tab.dataset.loaded) &&
                    !text.includes("Loading") &&
                    text.includes(expectedText);
                """,
                tab_target,
                expected_text,
            )
        )

    def get_stable_naturaltime_timestamp(self) -> datetime:
        """Return a recent timestamp that renders consistently in screenshots."""
        return timezone.now() - timedelta(minutes=1)

    def stabilize_stats_timestamp(self, stats: BaseStats) -> None:
        """Freeze an existing stats cache timestamp for screenshots."""
        data = stats.load().copy()
        if not data:
            return
        data["stats_timestamp"] = self.get_stable_naturaltime_timestamp().timestamp()
        stats.set_data(data)
        stats.save(update_parents=False)

    def stabilize_global_stats_timestamp(self) -> None:
        """Freeze global stats cache timestamp for activity screenshots."""
        self.stabilize_stats_timestamp(GlobalStats())

    def use_screenshot_site_domain_for_git_export(self, component: Component) -> None:
        """Store the displayed Git export URL with the screenshot domain."""
        with override_settings(SITE_DOMAIN=SCREENSHOT_SITE_DOMAIN, ENABLE_HTTPS=False):
            component.git_export = get_export_url(component)
            component.save(update_fields=("git_export",))

    def wait_for_screenshot_ready(self, timeout: int = 10) -> None:
        """Wait for browser-side rendering that can affect screenshots."""
        WebDriverWait(self.driver, timeout).until(self.is_page_loaded)
        self.driver.execute_script(
            """
            for (const image of document.images) {
                if (image.loading === "lazy") {
                    image.loading = "eager";
                }
            }
            """
        )
        self.driver.execute_async_script(
            """
            const done = arguments[0];
            if (!document.fonts) {
                done(true);
                return;
            }
            document.fonts.ready.then(() => done(true), () => done(false));
            """
        )
        WebDriverWait(self.driver, timeout).until(
            lambda driver: driver.execute_script(
                """
                const imagesLoaded = Array.from(document.images).every((image) => {
                    const source = image.getAttribute("src");
                    return !source || (image.complete && image.naturalWidth > 0);
                });
                const ajaxIdle =
                    typeof window.__weblateActiveFetches === "undefined" ||
                    window.__weblateActiveFetches === 0;
                const loadingIdle = Array.from(
                    document.querySelectorAll('[id^="loading-"]')
                ).every((element) => {
                    const style = getComputedStyle(element);
                    return (
                        style.display === "none" ||
                        style.visibility === "hidden" ||
                        Number(style.opacity) === 0 ||
                        element.offsetParent === null
                    );
                });
                const animationsIdle =
                    !document.getAnimations ||
                    document.getAnimations({ subtree: true }).every((animation) => {
                        const target = animation.effect?.target;
                        if (!(target instanceof Element)) {
                            return true;
                        }
                        const style = getComputedStyle(target);
                        if (
                            style.display === "none" ||
                            style.visibility === "hidden" ||
                            Number(style.opacity) === 0
                        ) {
                            return true;
                        }
                        const timing = animation.effect.getComputedTiming();
                        return (
                            timing.iterations === Infinity ||
                            !["pending", "running"].includes(animation.playState)
                        );
                    });
                return imagesLoaded && ajaxIdle && loadingIdle && animationsIdle;
                """
            )
        )
        self.driver.execute_async_script(
            """
            const done = arguments[0];
            let lastSnapshot = null;
            let stableFrames = 0;

            function snapshot() {
                const body = document.body;
                const doc = document.documentElement;
                return [
                    window.scrollX,
                    window.scrollY,
                    body?.scrollWidth,
                    body?.scrollHeight,
                    body?.offsetWidth,
                    body?.offsetHeight,
                    doc?.scrollWidth,
                    doc?.scrollHeight,
                    doc?.offsetWidth,
                    doc?.offsetHeight,
                    doc?.clientWidth,
                    doc?.clientHeight,
                ].join(":");
            }

            function check() {
                const currentSnapshot = snapshot();
                if (currentSnapshot === lastSnapshot) {
                    stableFrames += 1;
                } else {
                    stableFrames = 0;
                    lastSnapshot = currentSnapshot;
                }
                if (stableFrames >= 3) {
                    done(true);
                    return;
                }
                requestAnimationFrame(check);
            }

            requestAnimationFrame(check);
            """
        )

    def screenshot(self, name: str) -> None:
        """Capture named full page screenshot."""
        self.driver.set_window_size(1200, 1024)
        self.scroll_top()
        self.wait_for_screenshot_ready()
        dimensions = self.driver.execute_script(
            """
            const body = document.body;
            const doc = document.documentElement;
            return {
                width: Math.max(
                    body.scrollWidth,
                    body.offsetWidth,
                    body.clientWidth,
                    doc.scrollWidth,
                    doc.offsetWidth,
                    doc.clientWidth
                ),
                height: Math.max(
                    body.scrollHeight,
                    body.offsetHeight,
                    doc.scrollHeight,
                    doc.offsetHeight
                ),
            };
            """
        )
        self.driver.set_window_size(
            max(1200, math.ceil(dimensions["width"])),
            math.ceil(dimensions["height"] + 180),
        )
        self.scroll_top()
        self.wait_for_screenshot_ready()
        Path(os.path.join(self.image_path, name)).write_bytes(
            self.driver.get_screenshot_as_png()
        )

    def use_live_server_widget_preview(self) -> None:
        """Load widget preview from the live server while displaying public URLs."""
        protocol = "https" if settings.ENABLE_HTTPS else "http"
        display_site_url = f"{protocol}://{SCREENSHOT_SITE_DOMAIN}"
        self.driver.execute_script(
            """
            const image = document.getElementById("widget-image");
            if (image !== null) {
                image.src = image.src.replace(arguments[0], arguments[1]);
            }
            """,
            display_site_url,
            self.live_server_url,
        )
        WebDriverWait(self.driver, 10).until(
            lambda driver: driver.execute_script(
                """
                const image = document.getElementById("widget-image");
                return image === null || (image.complete && image.naturalWidth > 0);
                """
            )
        )

    @contextmanager
    def stable_performance_report_inputs(self) -> Iterator[None]:
        """Use deterministic server-side values for the performance screenshot."""
        original_wsgi_request_init = WSGIRequest.__init__
        missing = object()
        original_celery_encoding = cache.get("celery_encoding", missing)
        original_celery_latency = cache.get("celery_latency", missing)
        cache.set("celery_encoding", ("utf-8", "utf-8"))
        cache.set("celery_latency", 3)

        def wsgi_request_init(request, environ) -> None:
            original_wsgi_request_init(request, environ)
            request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_host(_request) -> str:
            return SCREENSHOT_SITE_DOMAIN

        def is_secure(_request) -> bool:
            return False

        def measure_database_latency() -> int:
            return 5

        def measure_cache_latency() -> int:
            return 1

        try:
            with (
                override_settings(
                    SITE_DOMAIN=SCREENSHOT_SITE_DOMAIN, ENABLE_HTTPS=False
                ),
                patch.object(WSGIRequest, "__init__", wsgi_request_init),
                patch.object(
                    HttpRequest,
                    "headers",
                    new=property(lambda _: PERFORMANCE_REPORT_HEADERS.copy()),
                ),
                patch.object(HttpRequest, "get_host", get_host),
                patch.object(HttpRequest, "is_secure", is_secure),
                patch(
                    "weblate.wladmin.views.disk_usage",
                    return_value=PERFORMANCE_REPORT_DISK_USAGE,
                ),
                patch(
                    "weblate.wladmin.views.get_queue_stats",
                    return_value={
                        "backup": 0,
                        "celery": 0,
                        "memory": 0,
                        "notify": 0,
                        "translate": 0,
                    },
                ),
                patch(
                    "weblate.wladmin.views.measure_database_latency",
                    measure_database_latency,
                ),
                patch(
                    "weblate.wladmin.views.measure_cache_latency",
                    measure_cache_latency,
                ),
                patch(
                    "weblate.wladmin.views.get_database_size",
                    return_value=123456789,
                ),
                patch(
                    "weblate.wladmin.views.get_database_disk_usage",
                    return_value=None,
                ),
            ):
                yield
        finally:
            if original_celery_encoding is missing:
                cache.delete("celery_encoding")
            else:
                cache.set("celery_encoding", original_celery_encoding)
            if original_celery_latency is missing:
                cache.delete("celery_latency")
            else:
                cache.set("celery_latency", original_celery_latency)

    def click(self, element: WebElement | str = "", htmlid: str | None = None) -> None:
        """Click on element and scroll it into view."""
        try:
            if htmlid:
                element = self.driver.find_element(By.ID, htmlid)
            if isinstance(element, str):
                element = self.driver.find_element(By.LINK_TEXT, element)
        except NoSuchElementException:
            # ruff: ignore[print]
            print(self.driver.page_source)
            raise

        try:
            element.click()
        except ElementNotVisibleException:
            self.actions.move_to_element(element).perform()
            element.click()
        except ElementClickInterceptedException:
            wait = WebDriverWait(self.driver, timeout=2)
            wait.until(lambda _: element.is_displayed())
            self.actions.move_to_element(element).perform()
            element.click()

    def select_component_license(self, license_id: str) -> None:
        inherit_license = self.driver.find_element(By.ID, "id_inherit_license")
        if inherit_license.is_selected():
            self.click(inherit_license)
        Select(self.driver.find_element(By.ID, "id_license")).select_by_value(
            license_id
        )

    def upload_file(self, element: WebElement, filename: str | Path) -> None:
        name: str
        exists: bool
        if isinstance(filename, Path):
            name = filename.as_posix()
            exists = filename.exists()
        else:
            name = os.path.abspath(filename)
            exists = os.path.exists(filename)
        if not exists:
            msg = f"Test file not found: {filename}"
            raise ValueError(msg)
        element.send_keys(name)

    @overload
    def do_login(self, *, create: Literal[False], superuser: bool = False) -> None: ...
    @overload
    def do_login(
        self, *, create: Literal[True] = True, superuser: bool = False
    ) -> User: ...
    def do_login(self, *, create=True, superuser=False):
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
        username_input = self.driver.find_element(By.ID, "id_username")
        username_input.send_keys("weblate@example.org")
        password_input = self.driver.find_element(By.ID, "id_password")
        password_input.send_keys("testpassword")

        with self.wait_for_page_load():
            self.click(self.driver.find_element(By.XPATH, '//input[@value="Sign in"]'))
        return user

    @overload
    def open_manage(self, *, login: Literal[True] = True) -> User: ...
    @overload
    def open_manage(self, *, login: Literal[False]) -> None: ...
    def open_manage(self, *, login=True):
        # Login as superuser
        user = self.do_login(superuser=True) if login else None

        # Open admin page
        with self.wait_for_page_load():
            self.click(htmlid="admin-button")
        return user

    @overload
    def open_admin(self, *, login: Literal[True] = True) -> User: ...
    @overload
    def open_admin(self, *, login: Literal[False]) -> None: ...
    def open_admin(self, *, login=True):
        user = self.open_manage(login=login)
        with self.wait_for_page_load():
            self.click("Tools")
        with self.wait_for_page_load():
            self.click("Django admin interface")
        return user

    def test_failed_login(self) -> None:
        self.do_login(create=False)

        # We should end up on login page as user was invalid
        self.driver.find_element(By.ID, "id_username")

    def test_login_form_accessibility(self) -> None:
        """Check labels and keyboard order on the public sign-in form."""
        with self.wait_for_page_load():
            self.click(htmlid="login-button")

        self.assert_labeled_control("id_username", "Username or e-mail")
        self.assert_labeled_control("id_password", "Password")

        username_input = self.driver.find_element(By.ID, "id_username")
        username_input.click()
        username_input.send_keys(Keys.TAB)
        self.assertEqual(
            self.driver.switch_to.active_element.get_attribute("id"),
            "id_password",
        )

        self.driver.switch_to.active_element.send_keys(Keys.TAB)
        submit_button = self.driver.switch_to.active_element
        self.assertEqual(submit_button.get_attribute("type"), "submit")
        self.assertEqual(submit_button.get_attribute("value"), "Sign in")

    def test_slug_autofill(self) -> None:
        """Check that base JavaScript initializes slug autogeneration."""
        self.do_login(superuser=True)

        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{reverse('create-project')}")

        name_input = self.driver.find_element(By.ID, "id_name")
        slug_input = self.driver.find_element(By.ID, "id_slug")
        name_input.send_keys("Example.Project Name")

        WebDriverWait(self.driver, 5).until(
            lambda _driver: slug_input.get_attribute("value") == "example-project-name"
        )

    def test_js_unit_tests(self) -> None:
        self.assertEqual(self.driver.execute_script("return getNumber('1,23');"), 1.23)
        self.assertEqual(self.driver.execute_script("return getNumber('1.23');"), 1.23)
        self.assertIsNone(
            self.driver.execute_script("return getNumber('not-a-number');")
        )

        self.assertEqual(
            self.driver.execute_script("return quoteSearch('simple');"), "simple"
        )
        self.assertEqual(
            self.driver.execute_script("return quoteSearch('two words');"),
            '"two words"',
        )

        self.assertEqual(self.driver.execute_script("return compareCells(1, 2);"), -1)
        self.assertEqual(
            self.driver.execute_script("return compareCells('2,5%', '1,0%');"), 1
        )
        self.assertEqual(
            self.driver.execute_script("return compareCells('abc', 'Abc');"), 0
        )

        self.assertEqual(
            self.driver.execute_script(
                "const cell = document.createElement('td'); cell.setAttribute('data-value', 'x-val'); return extractText(cell);"
            ),
            "x-val",
        )
        self.assertEqual(
            self.driver.execute_script(
                "const cell = document.createElement('td'); cell.textContent = 'inner'; return extractText(cell);"
            ),
            "inner",
        )

    def test_hotkeys(self) -> None:
        """Test hotkeys functionality."""
        # Check that the hotkeys library is loaded and the filter is overridden by our wrapper.
        self.assertTrue(
            self.driver.execute_script(
                "return typeof window.hotkeys === 'function'"
                " && typeof window.hotkeys.filter === 'function';"
            )
        )

        # Why this test exists: the wrapper overrides hotkeys.filter to always
        # return true so bindings still fire inside inputs and textareas
        # (mousetrap-global-bind used to cover this). Dropping that override
        # would silently break every in-editor shortcut.
        self.driver.execute_script(
            """
            window.__hotkeyFired = 0;
            window.hotkeys('ctrl+alt+b', () => {
                window.__hotkeyFired += 1;
                return false;
            });
            const ta = document.createElement('textarea');
            ta.id = '__hotkey_test_ta';
            document.body.appendChild(ta);
            ta.focus();
            """
        )
        textarea = self.driver.find_element(By.ID, "__hotkey_test_ta")
        (
            self.actions.key_down(Keys.CONTROL)
            .key_down(Keys.ALT)
            .send_keys_to_element(textarea, "b")
            .key_up(Keys.ALT)
            .key_up(Keys.CONTROL)
            .perform()
        )
        self.assertEqual(self.driver.execute_script("return window.__hotkeyFired;"), 1)

        # Shift+/ on a non-input element opens the shortcuts help modal.
        body = self.driver.find_element(By.TAG_NAME, "body")
        self.actions.send_keys_to_element(body, "?").perform()
        WebDriverWait(self.driver, 5).until(
            lambda driver: (
                "show"
                in driver.find_element(By.ID, "shortcuts-modal").get_attribute("class")
            )
        )
        modal = self.driver.find_element(By.ID, "shortcuts-modal")
        self.assertEqual(modal.get_attribute("role"), "dialog")
        modal_label = modal.get_attribute("aria-labelledby")
        self.assertEqual(
            self.driver.find_element(By.ID, modal_label).text,
            "Keyboard shortcuts",
        )
        self.assertEqual(
            self.driver.execute_script(
                """
                const ids = Array.from(arguments[0].querySelectorAll("[id]"))
                    .map((element) => element.id);
                return ids.filter((id, index) => ids.indexOf(id) !== index);
                """,
                modal,
            ),
            [],
        )

    @override_settings(
        WEBLATE_MACHINERY=(
            *settings.WEBLATE_MACHINERY,
            "weblate.trans.tests.test_selenium.SeleniumDummyTranslation",
        )
    )
    def test_machinery_hotkeys_use_current_results(self) -> None:
        """Test that machinery hotkeys use current result rows."""
        identifier = SeleniumDummyTranslation.get_identifier()
        project = self.create_component()
        project.machinery_settings = dict.fromkeys(
            Setting.objects.get_settings_dict(SettingCategory.MT)
        )
        project.machinery_settings[identifier] = {}
        project.save(update_fields=["machinery_settings"])

        self.do_login(superuser=True)
        unit = (
            Unit.objects.filter(
                translation__component__project=project,
                translation__language_code="cs",
            )
            .exclude(source="")
            .first()
        )
        self.assertIsNotNone(unit)
        unit = cast("Unit", unit)

        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{unit.get_absolute_url()}")

        self.click(htmlid="toggle-machinery")
        WebDriverWait(self.driver, 10).until(
            lambda driver: (
                len(driver.find_elements(By.CSS_SELECTOR, "#machinery-translations tr"))
                == 2
            )
        )

        self.driver.execute_script(
            """
            const translations = document.getElementById("machinery-translations");
            translations.replaceChildren();
            ["stale replacement 1", "current replacement 2"].forEach((text, idx) => {
                const key = String((idx + 1) % 10);
                const row = document.createElement("tr");
                row.setAttribute("data-machinery-key", key);
                row.setAttribute("data-raw", JSON.stringify({
                    plural_forms: [0],
                    text: text,
                }));
                const numberCell = document.createElement("td");
                numberCell.className = "machinery-number";
                const kbd = document.createElement("kbd");
                kbd.textContent = key;
                numberCell.appendChild(kbd);
                row.appendChild(numberCell);
                const cloneCell = document.createElement("td");
                const cloneLink = document.createElement("a");
                cloneLink.className = "js-copy-machinery";
                cloneLink.textContent = "Clone";
                cloneCell.appendChild(cloneLink);
                row.appendChild(cloneCell);
                translations.appendChild(row);
            });
            document.querySelector(".translator .translation-editor").value = "";
            """
        )

        editor = self.driver.find_element(
            By.CSS_SELECTOR, ".translator .translation-editor"
        )
        editor.click()
        (
            self.actions.key_down(Keys.CONTROL)
            .send_keys("m")
            .key_up(Keys.CONTROL)
            .send_keys("2")
            .perform()
        )

        self.assertEqual(
            self.driver.execute_script(
                'return document.querySelector(".translator .translation-editor").value;'
            ),
            "current replacement 2",
        )

    @override_settings(
        WEBLATE_MACHINERY=(
            *settings.WEBLATE_MACHINERY,
            "weblate.machinery.dummy.DummyTranslation",
        )
    )
    def test_auto_translate_mt_ignores_persisted_component(self) -> None:
        """Test MT auto-translation with persisted component form state."""
        identifier = DummyTranslation.get_identifier()

        def clear_auto_translation_storage() -> None:
            with suppress(WebDriverException):
                self.driver.execute_script(
                    'window.localStorage.removeItem("auto-translation");'
                )

        self.addCleanup(clear_auto_translation_storage)

        project = self.create_component()
        project.machinery_settings = dict.fromkeys(
            Setting.objects.get_settings_dict(SettingCategory.MT)
        )
        project.machinery_settings[identifier] = {}
        project.save(update_fields=["machinery_settings"])

        target_component = project.component_set.get(slug="django")
        for index in range(28):
            Component.objects.create(
                name=f"Extra {index}",
                slug=f"extra-{index}",
                project=project,
                repo="weblate://weblateorg/language-names",
                filemask=f"extra/{index}/*.po",
                new_base=f"extra/{index}/django.pot",
                file_format="po",
                source_language=target_component.source_language,
            )

        self.do_login(superuser=True)
        self.driver.execute_script(
            """
            window.localStorage.setItem(
                "auto-translation",
                JSON.stringify({component: "missing-component"}),
            );
            """
        )

        self.open_component(component=target_component, project=project)
        self.click("Operations")
        self.click("Batch automatic translation")
        self.click(htmlid="id_auto_auto_source_1")
        WebDriverWait(self.driver, 10).until(
            lambda driver: driver.execute_script(
                """
                const engines = document.getElementById("id_auto_engines");
                return Boolean(engines && engines.tomselect);
                """
            )
        )
        self.driver.execute_script(
            """
            const engines = document.getElementById("id_auto_engines");
            engines.tomselect.addItem(arguments[0]);
            engines.dispatchEvent(new Event("change", {bubbles: true}));
            """,
            identifier,
        )
        query = self.driver.find_element(By.ID, "id_auto_q")
        query.clear()
        query.send_keys("state:empty")

        with self.wait_for_page_load():
            self.driver.find_element(
                By.CSS_SELECTOR, 'form[data-persist="auto-translation"]'
            ).submit()

        body = self.driver.find_element(By.TAG_NAME, "body").text
        self.assertIn("Automatic translation completed", body)
        self.assertNotIn("Error in parameter component", body)
        self.assertNotIn("Could not process form!", body)

    def test_login(self) -> None:
        # Do proper login with new user
        self.do_login()

        # Load profile
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="settings-button")

        # Wait for profile to load
        self.driver.find_element(By.ID, "notifications")

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
        self.driver.find_element(By.ID, "dashboard-return")

    def register_user(self) -> str:
        # registration page
        with self.wait_for_page_load():
            self.click(htmlid="register-button")

        # Fill in registration form
        self.driver.find_element(By.ID, "id_email").send_keys("weblate@example.org")
        self.driver.find_element(By.ID, "id_username").send_keys("test-example")
        self.driver.find_element(By.ID, "id_fullname").send_keys("Test Example")
        with self.wait_for_page_load():
            self.click(self.driver.find_element(By.XPATH, '//input[@value="Register"]'))

        # Wait for registration email
        loops = 0
        while not mail.outbox:
            time.sleep(0.2)
            loops += 1
            if loops > 20:
                break

        return self.assert_registration_mailbox()

    @override_settings(REGISTRATION_CAPTCHA=False)
    def test_register(self, clear=False) -> None:
        """Test registration."""
        url = self.register_user()

        # Delete all cookies
        if clear:
            try:
                self.driver.delete_all_cookies()
            except WebDriverException as error:
                # This usually happens when browser fails to delete some
                # of the cookies for whatever reason.
                warnings.warn(f"Ignoring: {error}", stacklevel=1)

        # Confirm account
        self.driver.get(url)
        if "Confirm registration" in self.driver.find_element(By.TAG_NAME, "body").text:
            self.screenshot("registration-confirmation.png")
            with self.wait_for_page_load():
                self.click(
                    self.driver.find_element(
                        By.CSS_SELECTOR, "form button[type='submit']"
                    )
                )

        # Check we got message
        self.assertIn(
            "You have activated", self.driver.find_element(By.TAG_NAME, "body").text
        )

        # Check we're signed in
        self.click(htmlid="user-dropdown")
        self.assertIn(
            "Test Example", self.driver.find_element(By.ID, "profile-name").text
        )

    def test_register_nocookie(self) -> None:
        """Test registration without cookies."""
        self.test_register(True)

    @override_settings(WEBLATE_GPG_IDENTITY="Weblate <weblate@example.com>")
    def test_gpg(self) -> None:
        self.install_selenium_ssh_keys()
        gpg_key = Path(get_test_file("selenium-keys/weblate-public.asc")).read_text(
            encoding="utf-8"
        )
        with (
            patch(
                "weblate.trans.views.about.get_gpg_public_key",
                return_value=gpg_key,
            ),
            patch(
                "weblate.trans.views.about.get_gpg_sign_key",
                return_value=SELENIUM_GPG_KEY_ID,
            ),
        ):
            with self.wait_for_page_load():
                self.click(self.driver.find_element(By.ID, "footer-about-link"))
            with self.wait_for_page_load():
                self.click(self.driver.find_element(By.PARTIAL_LINK_TEXT, "Keys"))
            self.screenshot("about-gpg.png")

    def test_ssh(self) -> None:
        """Test SSH admin interface."""
        self.install_selenium_ssh_keys()
        self.open_manage()

        # Open SSH page
        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{reverse('manage-ssh')}")

        # Add SSH host key
        self.driver.find_element(By.ID, "id_host").send_keys("example.com")
        with (
            patch.dict(
                os.environ,
                {"PATH": f"{get_test_file('')}:{os.environ.get('PATH', '')}"},
            ),
            self.wait_for_page_load(),
        ):
            self.click(htmlid="ssh-add-button")

        self.screenshot("ssh-keys-added.png")

        # Open SSH page for final screenshot
        with self.wait_for_page_load():
            self.click("SSH keys")
        self.screenshot("ssh-keys.png")

    def create_component(self) -> Project:
        self.clear_weblateorg_fixture_path()
        project = Project.objects.create(name="WeblateOrg", slug="weblateorg")
        Component.objects.create(
            name="Language names",
            slug="language-names",
            project=project,
            repo="https://github.com/WeblateOrg/demo.git",
            branch="main",
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
        self.clear_project_stats_cache(project)
        return project

    def create_glossary(
        self, user: User, project: Project, language: Language
    ) -> Translation:
        glossary: Translation = project.glossaries[0].translation_set.get(
            language=language
        )
        glossary.add_unit(
            None, "", "machine translation", "strojový překlad", author=user
        )
        glossary.add_unit(None, "", "project", "projekt", author=user)
        return glossary

    def view_site(self) -> None:
        with self.wait_for_page_load():
            self.click(htmlid="return-to-weblate")

    def open_project(self, project: Project | str = "WeblateOrg") -> None:
        """Open project dashboard from the global project menu."""
        project_name = project.name if isinstance(project, Project) else project
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click(project_name)

    def open_component(
        self,
        component: Component | str = "Language names",
        project: Project | str = "WeblateOrg",
    ) -> None:
        """Open component dashboard from a project dashboard."""
        component_name = (
            component.name if isinstance(component, Component) else component
        )
        self.open_project(project)
        self.click("Components")
        with self.wait_for_page_load():
            self.click(component_name)

    def open_translation(
        self,
        language: str = "Czech",
        component: str = "Django",
        project: Project | str = "WeblateOrg",
    ) -> None:
        """Open a translation dashboard from a project dashboard."""
        self.open_project(project)
        with self.wait_for_page_load():
            self.click(language)
        self.click("Components")
        with self.wait_for_page_load():
            self.click(component)

    def create_android_component(self, project: Project) -> Component:
        """Create Android component used by translation screenshots."""
        component = Component.objects.create(
            name="Android",
            slug="android",
            project=project,
            repo="weblate://weblateorg/language-names",
            filemask="app/src/main/res/values-*/strings.xml",
            template="app/src/main/res/values/strings.xml",
            file_format="aresource",
        )
        self.clear_project_stats_cache(project)
        return component

    def test_dashboard(self) -> None:
        self.do_login()
        self.create_component()
        # Generate nice changes data
        for day in range(365):
            for _unused in range(int(10 + 10 * math.sin(2 * math.pi * day / 30))):
                change = Change.objects.create(action=ActionEvents.CREATE_PROJECT)
                change.timestamp -= timedelta(days=day)
                change.save()

        # Screenshot search
        self.click("Search")
        self.screenshot("search.png")

        # Render activity
        with patch("django.utils.timezone.now", return_value=SCREENSHOT_DATE):
            self.populate_global_activity_metrics()
            self.click("Insights")
            with self.wait_for_page_load():
                self.click("Statistics")
            self.stabilize_global_stats_timestamp()
            with self.wait_for_page_load():
                self.driver.refresh()
            self.screenshot("activity.png")

    @override_settings(PRIVATE_COMMIT_NAME_TEMPLATE="{site_title} user")
    @social_core_override_settings(AUTHENTICATION_BACKENDS=TEST_BACKENDS)
    def test_auth_backends(self) -> None:
        user = self.do_login()
        user.social_auth.create(provider="google-oauth2", uid=user.email)
        user.social_auth.create(provider="github", uid="123456")
        user.social_auth.create(provider="bitbucket", uid="weblate")
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="settings-button")
        self.click("Account")
        self.screenshot("authentication.png")
        self.assert_text_contains(".second-factor", "Security keys")

    def test_screenshot_filemask_repository_filename(self) -> None:
        """Test of mask of files to allow discovery/update of screenshots."""
        self.create_component()
        self.do_login(superuser=True)
        self.open_component("Django")
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Screenshots")
        self.click("Add screenshot")
        self.assert_text_contains("#screenshots-add", "Repository path to screenshot")
        self.screenshot("screenshot-filemask-repository-filename.png")

    def test_screenshots(self) -> None:
        """Screenshot tests."""
        # Make sure tesseract data is present and not downloaded at request time
        # what will cause test timeout.
        ensure_tesseract_language("eng")

        user = self.do_login(superuser=True)

        text = (
            "Automatic translation via machine translation uses active "
            "machine translation engines to get the best possible "
            "translations and applies them in this project."
        )
        project = self.create_component()
        language = Language.objects.get(code="cs")

        source = cast(
            "Unit",
            Unit.objects.get(source=text, translation__language=language).source_unit,
        )
        component = source.translation.component
        source.explanation = "Help text for automatic translation tool"
        source.save()
        self.create_glossary(user, project, language)
        component.alert_set.all().delete()

        def capture_unit(name, tab) -> None:
            unit = Unit.objects.get(source=text, translation__language=language)
            with self.wait_for_page_load():
                self.driver.get(f"{self.live_server_url}{unit.get_absolute_url()}")
            self.click(htmlid=tab)
            self.screenshot(name)
            with self.wait_for_page_load():
                self.click("Dashboard")

        def wait_search(expected_pk: int | None = None) -> None:
            time.sleep(0.1)
            if expected_pk is None:
                WebDriverWait(self.driver, 15).until(
                    presence_of_element_located(
                        (
                            By.XPATH,
                            (
                                '//div[@id="search-results"]'
                                '//tbody[@class="unit-listing-body"]//tr'
                            ),
                        )
                    )
                )
            else:
                WebDriverWait(self.driver, 15).until(
                    presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            f'#search-results .add-string[data-pk="{expected_pk}"]',
                        )
                    )
                )

        capture_unit("source-information.png", "toggle-nearby")
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Components")
        with self.wait_for_page_load():
            self.click("Django")
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Screenshots")

        # Upload screenshot
        self.click("Add screenshot")
        self.driver.find_element(By.ID, "id_name").send_keys("Automatic translation")
        element = self.driver.find_element(By.ID, "id_image")
        self.upload_file(element, get_test_file("screenshot.png"))
        with self.wait_for_page_load():
            element.submit()
        uploaded_screenshot = Screenshot.objects.get(name="Automatic translation")

        with open(get_test_file("screenshot.png"), "rb") as handle:
            listing_screenshot = Screenshot.objects.create(
                name="Main menu",
                repository_filename="fastlane/metadata/android/en-US/images/menu.png",
                image=File(handle, name="main-menu.png"),
                translation=component.source_translation,
                user=user,
            )
        listing_screenshot.add_unit(source, user)

        with self.wait_for_page_load():
            self.driver.get(
                f"{self.live_server_url}"
                f"{reverse('screenshots', kwargs={'path': component.get_url_path()})}"
            )
        self.assert_text_contains(".tab-content", "Automatic translation")
        self.assert_text_contains(".tab-content", "Main menu")
        self.assert_text_contains(".tab-content", "fastlane")
        self.screenshot("screenshot-listing.png")

        Screenshot.objects.update(timestamp=self.get_stable_naturaltime_timestamp())
        with self.wait_for_page_load():
            self.click("Automatic translation")

        # Perform OCR
        self.click(htmlid="screenshots-auto")
        wait_search()

        self.screenshot("screenshot-ocr.png")

        # Add string manually
        search_input = self.driver.find_element(By.ID, "search-input")
        search_input.clear()
        search_input.send_keys(f"{text!r}")
        self.click(htmlid="screenshots-search")
        wait_search(source.pk)
        self.click(
            self.driver.find_element(
                By.CSS_SELECTOR, f'#search-results .add-string[data-pk="{source.pk}"]'
            )
        )
        WebDriverWait(self.driver, 15).until(
            lambda _driver: (
                Screenshot.objects.get(pk=uploaded_screenshot.pk)
                .units.filter(pk=source.pk)
                .exists()
            )
        )

        # Unit should have screenshot assigned now
        capture_unit("screenshot-context.png", "toggle-machinery")

    def test_admin(self) -> None:
        """Test admin dashboard and announcements."""
        ConfigurationError.objects.create(
            name="test", message="Testing configuration error"
        )
        self.do_login(superuser=True)
        self.screenshot("admin-wrench.png")
        project = self.create_component()
        language = Language.objects.get(code="cs")
        Announcement.objects.create(
            project=project,
            message="Translations will be used only if they reach 60%.",
        )
        Announcement.objects.create(
            language=language, message="Czech translators rock!"
        )

        # Announcement display
        self.open_project(project)
        self.assert_text_contains(".announcement", "60%")
        self.click("Operations")
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
        self.assert_text_contains(".announcement", "Czech translators rock!")

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_workspaces(self) -> None:
        """Test workspaces management interface."""
        workspace = Workspace.objects.create(name="Localization workspace")
        Project.objects.create(
            name="Website translations",
            slug="website-translations",
            web="https://example.com/",
            workspace=workspace,
        )
        Project.objects.create(
            name="Mobile application",
            slug="mobile-application",
            web="https://example.com/mobile/",
            workspace=workspace,
        )
        Project.objects.create(
            name="Documentation portal",
            slug="documentation-portal",
            web="https://example.com/docs/",
            workspace=workspace,
        )

        user = self.do_login(superuser=True)
        workspace.add_owner(user)

        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{reverse('manage-workspaces')}")

        self.assert_text_contains("h4.card-title", "Manage workspaces")
        self.assert_text_contains("table.table-striped", "Localization workspace")
        self.assert_text_contains("table.table-striped", "3")

        with self.wait_for_page_load():
            self.click("Add workspace")
        self.assert_labeled_control("id_name", "Workspace name")
        self.driver.find_element(By.ID, "id_name").send_keys("Documentation workspace")
        with self.wait_for_page_load():
            self.driver.find_element(By.ID, "id_name").submit()

        self.assertTrue(
            Workspace.objects.filter(name="Documentation workspace").exists()
        )

        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{reverse('manage-workspaces')}")
        self.screenshot("workspaces.png")

        with self.wait_for_page_load():
            self.click("Localization workspace")
        self.assert_text_contains(".nav-pills", "Projects")
        self.assert_text_contains(".tab-content", "Website translations")
        self.assert_text_contains(".tab-content", "Mobile application")
        self.assert_text_contains(".tab-content", "Documentation portal")
        self.screenshot("workspace-projects.png")

        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Access control")
        self.assert_text_contains("table.table-striped", "Owners")
        self.assert_text_contains("table.table-striped", "Project creators")
        self.screenshot("workspace-access.png")

    def test_project_operations(self) -> None:
        """Test project-level screenshots."""
        project = self.create_component()
        self.do_login(superuser=True)
        self.open_project(project)

        self.screenshot("project-overview.png")

        # User management
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Users")
        invited_user = create_another_user()
        element = self.driver.find_element(By.ID, "id_project_add_user_user")
        element.send_keys(invited_user.username)
        # Typing starts an autocomplete request using the same session; let it
        # finish before submitting so it can not race one-shot flash messages.
        user_choice = WebDriverWait(self.driver, 5).until(
            lambda driver: next(
                (
                    result
                    for result in driver.find_elements(
                        By.CSS_SELECTOR, ".autoComplete_result"
                    )
                    if invited_user.username in result.text
                ),
                None,
            )
        )
        self.click(user_choice)
        Select(
            self.driver.find_element(By.ID, "id_project_add_user_group")
        ).select_by_index(1)
        with self.wait_for_page_load():
            element.submit()
        self.assert_text_contains(
            ".alert .task-message", "User invitation e-mail was sent."
        )
        self.assertTrue(
            invited_user.invitation_set.filter(
                group__defining_project__name="WeblateOrg"
            ).exists()
        )
        self.screenshot("manage-users.png")
        self.assertGreater(self.count_elements("table.table-striped tbody tr"), 0)

        # Automatic suggestions
        self.open_project(project)
        self.click("Operations")
        hidden_machinery_services = {
            "weblate.machinery.dummy.DummyTranslation",
            "weblate.trans.tests.test_selenium.SeleniumDummyTranslation",
        }
        machinery_services = tuple(
            path
            for path in settings.WEBLATE_MACHINERY
            if path not in hidden_machinery_services
        )
        with override_settings(WEBLATE_MACHINERY=machinery_services):
            with self.wait_for_page_load():
                self.click("Automatic suggestions")
            self.screenshot("project-machinery.png")

        # Access control settings
        self.open_project(project)
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Settings")
        self.click("Access")
        self.screenshot("project-access.png")
        self.click("Workflow")
        self.screenshot("project-workflow.png")

        # Engage page
        self.open_project(project)
        self.click("Community")
        with override_settings(SITE_DOMAIN=SCREENSHOT_SITE_DOMAIN):
            with self.wait_for_page_load():
                self.click("Status widgets")
            self.use_live_server_widget_preview()
            self.screenshot("promote.png")
        with self.wait_for_page_load():
            self.driver.get(
                f"{self.live_server_url}"
                f"{reverse('engage', kwargs={'path': project.get_url_path()})}"
            )
        self.screenshot("engage.png")
        with self.wait_for_page_load():
            self.click(htmlid="engage-project")

    def test_component_operations(self) -> None:
        """Test component operation screenshots."""
        language_regex = "^(cs|he|hu)$"
        project = self.create_component()
        component = Component.objects.get(project=project, slug="language-names")
        self.use_screenshot_site_domain_for_git_export(component)
        self.do_login(superuser=True)
        self.open_component(component, project)

        # Repository
        self.click("Operations")
        self.click("Repository maintenance")
        self.wait_for_ajax_tab("#repository", "Repository status")
        self.click("Operations")
        self.screenshot("component-repository.png")

        # Add-ons
        with self.wait_for_page_load():
            self.click("Add-ons")
        self.screenshot("addons.png")
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element(
                    By.XPATH, '//button[@data-addon="weblate.discovery.discovery"]'
                )
            )
        element = self.driver.find_element(By.ID, "id_match")
        element.send_keys(
            "weblate/locale/(?P<language>[^/]*)/LC_MESSAGES/(?P<component>[^/]*)\\.po"
        )
        element = self.driver.find_element(By.ID, "id_language_regex")
        element.clear()
        element.send_keys(language_regex)
        self.driver.find_element(By.ID, "id_new_base_template").send_keys(
            "weblate/locale/{{ component }}.pot"
        )
        element = self.driver.find_element(By.ID, "id_name_template")
        element.clear()
        element.send_keys("{{ component|title }}")
        Select(self.driver.find_element(By.ID, "id_file_format")).select_by_value("po")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("addon-discovery.png")
        element = self.driver.find_element(By.ID, "id_confirm")
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

        # Component tools
        self.open_component(component, project)
        self.click("Operations")
        self.click("Search and replace")
        self.assert_text_contains("#replace", "Search and replace")
        self.screenshot("search-replace.png")
        self.click("Operations")
        self.click("Bulk edit")
        self.assert_text_contains("#bulk-edit", "Bulk edit")
        self.screenshot("bulk-edit.png")

        with self.wait_for_page_load():
            self.driver.get(
                f"{self.live_server_url}"
                f"{reverse('matrix', kwargs={'path': component.get_url_path()})}"
                "?lang=cs&lang=he"
            )
        WebDriverWait(self.driver, 15).until(
            presence_of_element_located((By.CSS_SELECTOR, ".matrix tbody tr"))
        )
        self.screenshot("matrix-view.png")

        # Contributor license agreement
        self.open_component(component, project)
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Settings")
        inherit_agreement = self.driver.find_elements(By.ID, "id_inherit_agreement")
        if inherit_agreement and inherit_agreement[0].is_selected():
            self.click(inherit_agreement[0])
            WebDriverWait(self.driver, 5).until(
                lambda driver: driver.find_element(By.ID, "id_agreement").is_enabled()
            )
        element = self.driver.find_element(By.ID, "id_agreement")
        element.send_keys("This is an agreement.")
        with self.wait_for_page_load():
            element.submit()
        with self.wait_for_page_load():
            self.click("Language names")
        self.screenshot("contributor-agreement.png")
        with self.wait_for_page_load():
            self.click("View contributor license agreement")
        element = self.driver.find_element(By.ID, "id_confirm")
        self.click(element)
        with self.wait_for_page_load():
            element.submit()

    def test_translation_workflow(self) -> None:
        """Test translation workflow screenshots."""
        project = self.create_component()
        user = self.do_login(superuser=True)
        self.open_translation(project=project)
        self.screenshot("strings-to-check.png")
        count_text = self.driver.find_element(By.CSS_SELECTOR, ".card th.number").text
        self.assertGreater(int(count_text.replace(",", "")), 0)
        self.click("Files")
        self.click("Upload translation")
        self.click("Files")
        self.screenshot("file-upload.png")
        self.assert_text_contains("#upload", "File upload mode")
        self.screenshot("file-import-methods.png")
        self.click("Customize download")
        self.click("Files")
        self.screenshot("file-download.png")
        self.click("Operations")
        self.click("Batch automatic translation")
        self.click(htmlid="id_auto_auto_source_1")
        self.click("Operations")
        self.screenshot("automatic-translation.png")
        self.click("Search")
        element = self.driver.find_element(By.ID, "id_q")
        element.send_keys("'%(count)s word'")
        with self.wait_for_page_load():
            element.submit()
        self.click("History")
        self.screenshot("format-highlight.png")
        self.click("Comments")
        self.screenshot("plurals.png")

        # Test search dropdown
        dropdown = self.driver.find_element(By.ID, "query-dropdown")
        dropdown.click()
        time.sleep(0.2)
        self.screenshot("query-dropdown.png")
        with self.wait_for_page_load():
            self.click(
                self.driver.find_element(By.PARTIAL_LINK_TEXT, "Untranslated strings")
            )
        self.driver.find_element(By.ID, "id_34a4642999e44a2b_0")

        # Test sort dropdown
        sort = self.driver.find_element(By.ID, "query-sort-dropdown")
        sort.click()
        time.sleep(0.2)
        self.screenshot("query-sort.png")
        with self.wait_for_page_load():
            self.click("Position")

        # Return to original unit
        element = self.driver.find_element(By.ID, "id_q")
        element.clear()
        element.send_keys("'%(count)s word'")
        with self.wait_for_page_load():
            element.submit()

        # Trigger check
        self.driver.find_element(By.ID, "id_a2a808c8ccbece08_0").clear()
        element = self.driver.find_element(By.ID, "id_a2a808c8ccbece08_1")
        element.clear()
        element.send_keys("několik slov")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("checks.png")

        # Secondary language display
        user.profile.secondary_languages.set(Language.objects.filter(code__in=("he",)))
        with self.wait_for_page_load():
            self.click("Czech")
        with self.wait_for_page_load():
            self.click(self.driver.find_element(By.PARTIAL_LINK_TEXT, "All strings"))
        self.click(self.driver.find_element(By.PARTIAL_LINK_TEXT, "Other languages"))
        self.screenshot("secondary-language.png")

        # RTL translation
        with self.wait_for_page_load():
            self.click("Django")
        with self.wait_for_page_load():
            self.click("Hebrew")
        with self.wait_for_page_load():
            self.click(self.driver.find_element(By.PARTIAL_LINK_TEXT, "All strings"))
        self.screenshot("visual-keyboard.png")

        translation = Component.objects.get(
            project=project, slug="django"
        ).translation_set.get(language__code="he")
        with self.wait_for_page_load():
            self.driver.get(
                f"{self.live_server_url}"
                f"{reverse('zen', kwargs={'path': translation.get_url_path()})}"
                "?q=word"
            )
        WebDriverWait(self.driver, 15).until(
            presence_of_element_located((By.CSS_SELECTOR, ".zen-unit"))
        )
        self.screenshot("zen-mode.png")

    def test_profile_dashboard(self) -> None:
        """Test profile and dashboard screenshots."""
        project = self.create_component()
        components = project.component_set.all()
        components.update(license="GPL-3.0-or-later", inherit_license=False)
        language_names = components.get(slug="language-names")
        django = components.get(slug="django")
        language_names.agreement = (
            "Translations are contributed under the project license."
        )
        language_names.inherit_agreement = False
        language_names.save(update_fields=["agreement", "inherit_agreement"])
        user = self.do_login(superuser=True)

        languages = Language.objects.filter(code__in=("cs", "he", "hu"))
        user.profile.languages.set(languages)
        user.profile.watched.add(project)
        ContributorAgreement.objects.create(user=user, component=language_names)
        for translation in django.translation_set.filter(language__in=languages):
            Change.objects.create(
                action=ActionEvents.CHANGE,
                user=user,
                author=user,
                project=project,
                component=django,
                translation=translation,
                language=translation.language,
            )

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
        time.sleep(0.2)
        self.screenshot("your-translations.png")

    def test_team_management(self) -> None:
        """Test team management screenshots."""
        project = self.create_component()
        component_list = ComponentList.objects.create(
            name="Website components", slug="website-components"
        )
        component_list.components.set(project.component_set.all())
        team = Group.objects.create(name="Spanish Admin-Reviewers")
        team.roles.set(Role.objects.without_global_permissions()[:2])
        team.projects.set([project])
        team.componentlists.set([component_list])
        team.languages.set(Language.objects.filter(code__in=("cs", "he")))
        AutoGroup.objects.create(group=team, match=r".*@example\.org$")

        self.do_login(superuser=True)
        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{team.get_absolute_url()}")
        self.assert_text_contains("#basic", "Project selection")
        self.screenshot("team-scope.png")

        self.click("Automatic assignments")
        self.assertEqual(
            self.driver.find_element(By.ID, "id_autogroup_set-0-match").get_attribute(
                "value"
            ),
            r".*@example\.org$",
        )
        self.screenshot("team-automatic-assignments.png")

    @modify_settings(INSTALLED_APPS={"append": "weblate.billing"})
    def test_add_component(self) -> None:
        """Test user adding project and component."""
        self.clear_weblateorg_fixture_path()
        user = self.do_login()
        with patch("django.utils.timezone.now", return_value=SCREENSHOT_DATE):
            billing = create_test_billing(user, invoice=False)
            billing.invoice_set.create(
                amount=19,
                start=SCREENSHOT_DATE.date() - timedelta(days=1),
                end=SCREENSHOT_DATE.date() + timedelta(days=1),
            )

            # Open billing page
            self.click(htmlid="user-dropdown")
            with self.wait_for_page_load():
                self.click(htmlid="billing-button")
            self.screenshot("user-billing.png")

            # Click on add project
            with self.wait_for_page_load():
                self.click(
                    self.driver.find_element(By.CLASS_NAME, "billing-add-project")
                )

            # Add project
            self.driver.find_element(By.ID, "id_name").send_keys("WeblateOrg")
            self.driver.find_element(By.ID, "id_web").send_keys("https://weblate.org/")
            self.driver.find_element(By.ID, "id_instructions").send_keys(
                "https://weblate.org/contribute/"
            )
            self.screenshot("user-add-project.png")
            with self.wait_for_page_load():
                self.driver.find_element(By.ID, "id_name").submit()
            self.screenshot("user-add-project-done.png")
            self.assertIn("WeblateOrg", self.driver.title)

            # Click on add component
            with self.wait_for_page_load():
                self.click(self.driver.find_element(By.ID, "list-add-button"))

            # Add component
            self.driver.find_element(By.ID, "id_name").send_keys("Language names")
            self.driver.find_element(By.ID, "id_repo").send_keys(
                "https://github.com/WeblateOrg/demo.git"
            )
            self.driver.find_element(By.ID, "id_branch").send_keys("main")
            self.screenshot("user-add-component-init.png")
            with self.wait_for_page_load(timeout=1200):
                self.driver.find_element(By.ID, "id_name").submit()

            self.screenshot("user-add-component-discovery.png")
            discovery_choice = WebDriverWait(self.driver, 30).until(
                element_to_be_clickable((By.ID, "id_discovery_1"))
            )
            discovery_choice.click()
            with self.wait_for_page_load(timeout=1200):
                self.driver.find_element(By.ID, "id_name").submit()

            self.driver.find_element(By.ID, "id_repoweb").send_keys(
                "https://github.com/WeblateOrg/demo/blob/{{branch}}/{{filename}}#L{{line}}"
            )
            self.driver.find_element(By.ID, "id_filemask").send_keys(
                "weblate/langdata/locale/*/LC_MESSAGES/django.po"
            )
            self.driver.find_element(By.ID, "id_new_base").send_keys(
                "weblate/langdata/locale/django.pot"
            )
            Select(self.driver.find_element(By.ID, "id_file_format")).select_by_value(
                "po"
            )
            self.select_component_license("GPL-3.0-or-later")
            element = self.driver.find_element(By.ID, "id_language_regex")
            element.clear()
            element.send_keys("^(cs|he|hu)$")
            self.screenshot("user-add-component.png")

    def test_alerts(self) -> None:
        self.clear_weblateorg_fixture_path()
        project = Project.objects.create(name="WeblateOrg", slug="weblateorg")
        duplicates = Component.objects.create(
            name="Duplicates",
            slug="duplicates",
            project=project,
            repo="https://github.com/WeblateOrg/test.git",
            branch="main",
            filemask="po-duplicates/*.dpo",
            new_base="po-duplicates/hello.pot",
            file_format="po",
        )
        alert_timestamp = self.get_stable_naturaltime_timestamp()
        duplicates.alert_set.update(timestamp=alert_timestamp, updated=alert_timestamp)
        self.do_login(superuser=True)
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Components")
        with self.wait_for_page_load():
            self.click("Duplicates")
        self.click(
            self.driver.find_element(By.CSS_SELECTOR, 'a[data-bs-target="#alerts"]')
        )
        self.screenshot("alerts.png")
        self.assertGreater(self.count_elements("#alerts .card"), 0)

        guidance = Component.objects.create(
            name="Guidance",
            slug="guidance",
            project=project,
            repo="https://github.com/WeblateOrg/test.git",
            branch="main",
            filemask="po/*.po",
            file_format="po",
        )
        guidance.add_alert("MissingTranslationInstructions")
        self.driver.get(f"{self.live_server_url}{guidance.get_absolute_url()}")
        self.click(
            self.driver.find_element(By.CSS_SELECTOR, 'a[data-bs-target="#alerts"]')
        )
        self.screenshot("component-diagnostics.png")
        self.assert_text_contains("#alerts", "Define translation instructions")

    def test_fonts(self) -> None:
        self.create_component()
        self.do_login(superuser=True)
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Fonts")

        self.click(htmlid="tab_fonts")

        # Upload font
        element = self.driver.find_element(By.ID, "id_font")
        self.upload_file(element, FONT)
        with self.wait_for_page_load():
            self.click(htmlid="upload_font_submit")

        self.screenshot("font-edit.png")

        with self.wait_for_page_load():
            self.click("Fonts")

        # Upload second font
        element = self.driver.find_element(By.ID, "id_font")
        self.upload_file(element, FONT_SOURCE)
        with self.wait_for_page_load():
            self.click(htmlid="upload_font_submit")

        with self.wait_for_page_load():
            self.click("Fonts")

        self.screenshot("font-list.png")

        self.click(htmlid="tab_groups")

        # Create group
        Select(self.driver.find_element(By.ID, "id_group_font")).select_by_visible_text(
            "Source Sans 3 Bold"
        )
        element = self.driver.find_element(By.ID, "id_group_name")
        element.send_keys("default-font")
        with self.wait_for_page_load():
            element.submit()

        Select(self.driver.find_element(By.ID, "id_font")).select_by_visible_text(
            "Kurinto Sans Regular"
        )
        element = self.driver.find_element(By.ID, "id_language")
        Select(element).select_by_visible_text("Japanese")
        with self.wait_for_page_load():
            element.submit()
        Select(self.driver.find_element(By.ID, "id_font")).select_by_visible_text(
            "Kurinto Sans Regular"
        )
        element = self.driver.find_element(By.ID, "id_language")
        Select(element).select_by_visible_text("Korean")
        with self.wait_for_page_load():
            element.submit()

        self.screenshot("font-group-edit.png")

        with self.wait_for_page_load():
            self.click("Font groups")

        self.screenshot("font-group-list.png")

    def test_backup(self) -> None:
        fixed_timestamp = datetime(2026, 1, 6, 12, 0, tzinfo=UTC)
        display_repository = "ssh://weblate@backup.example.com/backups"
        display_passphrase = "example-backup-passphrase-for-screenshot-2026"

        self.create_temp()
        self.addCleanup(self.remove_temp)
        with patch("django.utils.timezone.now", return_value=fixed_timestamp):
            self.open_manage()
            with self.wait_for_page_load():
                self.click("Backups")
            element = self.driver.find_element(By.ID, "id_repository")
            element.send_keys(self.tempdir)
            with self.wait_for_page_load():
                element.submit()
            with self.wait_for_page_load():
                self.click(self.driver.find_element(By.NAME, "trigger"))

            service = BackupService.objects.get()
            service.repository = display_repository
            service.passphrase = display_passphrase
            service.timestamp = fixed_timestamp
            service.save(update_fields=("repository", "passphrase", "timestamp"))
            service.backuplog_set.update(timestamp=fixed_timestamp)

            with self.wait_for_page_load():
                self.driver.refresh()
            credentials = self.driver.find_element(
                By.CSS_SELECTOR, 'button[aria-controls$="-credentials"]'
            )
            credentials_id = cast("str", credentials.get_attribute("aria-controls"))
            self.click(credentials)
            WebDriverWait(self.driver, 5).until(
                lambda driver: (
                    "show"
                    in driver.find_element(By.ID, credentials_id).get_attribute("class")
                )
            )
            self.screenshot("backups.png")
            # The login session was created with the patched clock and expires
            # once the real clock is restored.
            SupportStatus.objects.create(secret="123", name="community")
            with self.wait_for_page_load():
                self.click("Weblate status")
            self.assert_text_contains("h4.card-title", "Weblate support status")
            self.screenshot("support-discovery.png")

    def test_manage(self) -> None:
        with (
            patch("weblate.wladmin.views.GIT_LINK", None),
            patch("weblate.wladmin.views.GIT_REVISION", None),
        ):
            self.open_manage()
            self.screenshot("support.png")
        with self.wait_for_page_load():
            self.click("Appearance")
        self.screenshot("appearance-settings.png")
        with self.stable_performance_report_inputs():
            with self.wait_for_page_load():
                self.click("Performance report")
            self.screenshot("performance-report.png")

    def test_explanation(self) -> None:
        project = self.create_component()
        self.create_android_component(project)

        self.do_login(superuser=True)
        self.click(htmlid="projects-menu")
        with self.wait_for_page_load():
            self.click("Browse all projects")
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Labels")
        element = self.driver.find_element(By.ID, "id_name")
        element.send_keys("Current sprint")
        self.click(self.driver.find_element(By.CLASS_NAME, "label-green"))
        with self.wait_for_page_load():
            element.submit()
        element = self.driver.find_element(By.ID, "id_name")
        element.send_keys("Next sprint")
        self.click(self.driver.find_element(By.CLASS_NAME, "label-aqua"))
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("labels.png")

        # Navigate to component
        with self.wait_for_page_load():
            self.click("WeblateOrg")
        self.click("Components")
        with self.wait_for_page_load():
            self.click("Android")

        # Edit variant configuration
        self.click("Operations")
        with self.wait_for_page_load():
            self.click("Settings")
        self.click("Translation")
        element = self.driver.find_element(By.ID, "id_variant_regex")
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
        element = self.driver.find_element(By.ID, "id_q")
        element.send_keys("Monday")
        with self.wait_for_page_load():
            element.submit()
        self.screenshot("source-review-detail.png")

        # Display variants
        self.click(htmlid="toggle-variants")
        self.screenshot("variants-translate.png")

        # Edit context
        self.click(htmlid="edit-context")
        WebDriverWait(self.driver, 10).until(
            lambda driver: driver.execute_script(
                "return document.activeElement?.id === 'id_explanation';"
            )
        )
        self.driver.execute_script(
            "document.getElementById('context-edit-form').focus({preventScroll: true});"
        )
        self.screenshot("source-review-edit.png")

        # Close modal dialog
        self.driver.find_element(By.ID, "id_extra_flags-ts-input").send_keys(
            Keys.ESCAPE
        )
        time.sleep(0.2)

    def test_dark_theme(self) -> None:
        project = self.create_component()
        self.create_android_component(project)
        self.do_login()
        self.click(htmlid="user-dropdown")
        with self.wait_for_page_load():
            self.click(htmlid="settings-button")
        self.click("Preferences")
        element = self.driver.find_element(By.ID, "id_theme")
        Select(element).select_by_visible_text("Dark")
        with self.wait_for_page_load():
            element.submit()
        time.sleep(0.2)
        self.screenshot("dark-theme.png")
        with self.wait_for_page_load():
            self.driver.get(f"{self.live_server_url}{project.get_absolute_url()}")
        self.screenshot("dark-theme-dashboard.png")
        with self.wait_for_page_load():
            self.click("Czech")
        self.screenshot("dark-theme-language.png")
        with self.wait_for_page_load():
            self.click("Translate")
        self.screenshot("dark-theme-translate.png")

    def test_glossary(self) -> None:
        user = self.do_login()
        project = self.create_component()
        language = Language.objects.get(code="cs")
        glossary = self.create_glossary(user, project, language)

        self.driver.get(f"{self.live_server_url}{glossary.get_absolute_url()}")
        self.screenshot("glossary-component.png")

        with self.wait_for_page_load():
            self.click("Czech")

        with self.wait_for_page_load():
            self.click("Browse")
        self.screenshot("glossary-browse.png")
        self.assertGreaterEqual(self.count_elements("tbody.unit-listing-body tr"), 2)

        with self.wait_for_page_load():
            self.click(self.driver.find_element(By.PARTIAL_LINK_TEXT, "projekt"))

        self.click(htmlid="unit_tools_dropdown")
        self.screenshot("glossary-tools.png")

    def test_date_range_picker(self) -> None:
        """Test date range picker."""
        self.do_login()
        start_date = SCREENSHOT_DATE.date()
        end_date = start_date + timedelta(days=6)
        period = f"{start_date:%m/%d/%Y} - {end_date:%m/%d/%Y}"
        self.driver.get(
            f"{self.live_server_url}{reverse('changes')}?{urlencode({'period': period})}"
        )

        period_input = self.driver.find_element(By.NAME, "period")
        picker = self.driver.find_element(By.CSS_SELECTOR, ".datepicker")

        self.assertEqual(picker.value_of_css_property("display"), "none")

        self.click(period_input)
        self.assertNotEqual(picker.value_of_css_property("display"), "none")
        self.screenshot("date-range-picker-open.png")

        period_input.send_keys(Keys.ESCAPE)
        self.assertEqual(picker.value_of_css_property("display"), "none")

        self.click(period_input)

        presets = self.driver.find_elements(By.CSS_SELECTOR, ".datepicker-preset")
        last_7_days = presets[2]
        self.click(last_7_days)

        value = period_input.get_attribute("value")
        self.assertRegex(value, r"\d{2}/\d{2}/\d{4} - \d{2}/\d{2}/\d{4}")

        self.assertEqual(picker.value_of_css_property("display"), "none")

        self.click(period_input)
        clear_btn = self.driver.find_element(By.CSS_SELECTOR, ".datepicker-btn-clear")
        self.click(clear_btn)

        self.assertEqual(period_input.get_attribute("value"), "")
        self.assertEqual(picker.value_of_css_property("display"), "none")

        self.click(period_input)

        title = self.driver.find_element(By.CSS_SELECTOR, ".datepicker-cal-title")
        initial_title = title.text

        prev_btn = self.driver.find_element(
            By.CSS_SELECTOR, ".datepicker-nav[aria-label='Previous month']"
        )
        self.click(prev_btn)

        title = self.driver.find_element(By.CSS_SELECTOR, ".datepicker-cal-title")
        self.assertNotEqual(title.text, initial_title)

        next_btn = self.driver.find_element(
            By.CSS_SELECTOR, ".datepicker-nav[aria-label='Next month']"
        )
        self.click(next_btn)
        # Need to find the button again otherwise selenium will complain about the element being stale
        next_btn = self.driver.find_element(
            By.CSS_SELECTOR, ".datepicker-nav[aria-label='Next month']"
        )
        self.click(next_btn)

        title = self.driver.find_element(By.CSS_SELECTOR, ".datepicker-cal-title")
        self.assertNotEqual(title.text, initial_title)

        # Click on the page body outside the picker
        self.driver.find_element(By.TAG_NAME, "label").click()

        self.assertEqual(picker.value_of_css_property("display"), "none")
