# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for translation views."""

from io import BytesIO
from urllib.parse import urlsplit
from zipfile import ZipFile

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.translation import activate
from PIL import Image

from weblate.auth.models import Group, get_anonymous, setup_project_groups
from weblate.lang.models import Language
from weblate.trans.models import Component, ComponentList, Project
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.utils import (
    create_another_user,
    create_test_user,
    wait_for_celery,
)
from weblate.utils.db import using_postgresql
from weblate.utils.hash import hash_to_checksum
from weblate.utils.xml import parse_xml


class RegistrationTestMixin:
    """Helper to share code for registration testing."""

    def assert_registration_mailbox(self, match=None):
        if match is None:
            match = "[Weblate] Your registration on Weblate"
        # Check mailbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, match)

        live_url = getattr(self, "live_server_url", None)

        # Parse URL
        for line in mail.outbox[0].body.splitlines():
            if "verification_code" not in line:
                continue
            if "(" in line or ")" in line or "<" in line or ">" in line:
                continue
            if live_url and line.startswith(live_url):
                return line + "&confirm=1"
            if line.startswith("http://example.com/"):
                return line[18:] + "&confirm=1"

        self.fail("Confirmation URL not found")
        return ""

    def assert_notify_mailbox(self, sent_mail):
        self.assertEqual(
            sent_mail.subject, "[Weblate] Activity on your account at Weblate"
        )


class ViewTestCase(RepoTestCase):
    @classmethod
    def setUpTestData(cls):
        get_anonymous.cache_clear()
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = create_test_user()
        group = Group.objects.get(name="Users")
        self.user.groups.add(group)
        # Create another user
        self.anotheruser = create_another_user()
        self.user.groups.add(group)
        # Create project to have some test base
        self.component = self.create_component()
        self.project = self.component.project
        self.translation = self.get_translation()
        # Invalidate caches
        self.project.stats.invalidate()
        cache.clear()
        # Login
        self.client.login(username="testuser", password="testpassword")
        # Prepopulate kwargs

    @property
    def kw_project(self):
        return {"project": self.project.slug}

    @property
    def kw_component(self):
        return {"path": self.component.get_url_path()}

    @property
    def kw_translation(self):
        return {"path": self.translation.get_url_path()}

    @property
    def translation_url(self):
        return self.translation.get_absolute_url()

    @property
    def project_url(self):
        return self.project.get_absolute_url()

    @property
    def component_url(self):
        return self.component.get_absolute_url()

    def tearDown(self):
        super().tearDown()
        # Reset to English language
        activate("en")

    def update_fulltext_index(self):
        wait_for_celery()

    def make_manager(self):
        """Make user a Manager."""
        # Sitewide privileges
        self.user.groups.add(Group.objects.get(name="Managers"))
        # Project privileges
        self.project.add_user(self.user, "Administration")

    def get_request(self, user=None):
        """Wrapper to get fake request object."""
        request = self.factory.get("/")
        request.user = user if user else self.user
        request.session = "session"
        messages = FallbackStorage(request)
        request._messages = messages
        return request

    def get_translation(self, language="cs"):
        return self.component.translation_set.get(language__code=language)

    def get_unit(
        self, source: str = "Hello, world!\n", language: str = "cs", translation=None
    ):
        if translation is None:
            translation = self.get_translation(language)
        return translation.unit_set.get(source__startswith=source)

    def change_unit(self, target, source="Hello, world!\n", language="cs", user=None):
        unit = self.get_unit(source, language)
        unit.target = target
        unit.save_backend(user or self.user)

    def edit_unit(
        self,
        source: str,
        target: str,
        language: str = "cs",
        follow: bool = False,
        translation=None,
        **kwargs,
    ):
        """Do edit single unit using web interface."""
        unit = self.get_unit(source, language, translation=translation)
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": target,
            "review": "20",
        }
        params.update(kwargs)
        return self.client.post(
            unit.translation.get_translate_url(), params, follow=follow
        )

    def assert_redirects_offset(self, response, exp_path, exp_offset):
        """Assert that offset in response matches expected one."""
        self.assertEqual(response.status_code, 302)

        # We don't use all variables
        _scheme, _netloc, path, query, _fragment = urlsplit(response["Location"])

        self.assertEqual(path, exp_path)

        exp_offset = f"offset={exp_offset:d}"
        self.assertIn(exp_offset, query)

    def assert_png(self, response):
        """Check whether response contains valid PNG image."""
        # Check response status code
        self.assertEqual(response.status_code, 200)
        self.assert_png_data(response.content)

    def assert_png_data(self, content):
        """Check whether data is PNG image."""
        # Try to load PNG with PIL
        image = Image.open(BytesIO(content))
        self.assertEqual(image.format, "PNG")

    def assert_zip(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        with ZipFile(BytesIO(response.content), "r") as zipfile:
            self.assertIsNone(zipfile.testzip())

    def assert_svg(self, response):
        """Check whether response is a SVG image."""
        # Check response status code
        self.assertEqual(response.status_code, 200)
        tree = parse_xml(response.content)
        self.assertEqual(tree.tag, "{http://www.w3.org/2000/svg}svg")

    def assert_backend(self, expected_translated, language="cs"):
        """Check that backend has correct data."""
        translation = self.get_translation(language)
        translation.commit_pending("test", None)
        store = translation.component.file_format_cls(translation.get_filename(), None)
        messages = set()
        translated = 0

        for unit in store.content_units:
            id_hash = unit.id_hash
            self.assertNotIn(id_hash, messages, "Duplicate string in in backend file!")
            if unit.is_translated():
                translated += 1

        self.assertEqual(
            translated,
            expected_translated,
            "Did not found expected number of translations ({} != {}).".format(
                translated, expected_translated
            ),
        )

    def log_as_jane(self):
        self.client.login(username="jane", password="testpassword")


class FixtureTestCase(ViewTestCase):
    @classmethod
    def setUpTestData(cls):
        """Manually load fixture."""
        # Ensure there are no Language objects, we add
        # them in defined order in fixture
        Language.objects.all().delete()

        # Stolen from setUpClass, we just need to do it
        # after transaction checkpoint and deleting languages
        for db_name in cls._databases_names(include_mirrors=False):
            call_command(
                "loaddata", "simple-project.json", verbosity=0, database=db_name
            )
        # Apply group project/language automation
        for group in Group.objects.iterator():
            group.save()

        super().setUpTestData()

    def clone_test_repos(self):
        return

    def create_project(self):
        project = Project.objects.all()[0]
        setup_project_groups(self, project)
        return project

    def create_component(self):
        component = self.create_project().component_set.all()[0]
        component.create_path()
        return component


class TranslationManipulationTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.component.new_lang = "add"
        self.component.save()

    def create_component(self):
        return self.create_po_new_base()

    def test_model_add(self):
        self.assertTrue(
            self.component.add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )
        self.assertTrue(
            self.component.translation_set.filter(language_code="af").exists()
        )

    def test_model_add_duplicate(self):
        request = self.get_request()
        self.assertFalse(get_messages(request))
        self.assertIsNone(
            self.component.add_new_language(Language.objects.get(code="de"), request)
        )
        self.assertTrue(get_messages(request))

    def test_model_add_disabled(self):
        self.component.new_lang = "contact"
        self.component.save()
        self.assertFalse(
            self.component.add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )

    def test_model_add_superuser(self):
        self.component.new_lang = "contact"
        self.component.save()
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(
            self.component.add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )

    def test_remove(self):
        translation = self.component.translation_set.get(language_code="de")
        translation.remove(self.user)
        # Force scanning of the repository
        self.component.create_translations()
        self.assertFalse(
            self.component.translation_set.filter(language_code="de").exists()
        )


class BasicViewTest(ViewTestCase):
    def test_view_project(self):
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "test/test")
        self.assertNotContains(response, "Spanish")

    def test_view_project_ghost(self):
        self.user.profile.languages.add(Language.objects.get(code="es"))
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "Spanish")

    def test_view_component(self):
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Test/Test")
        self.assertNotContains(response, "Spanish")

    def test_view_component_ghost(self):
        self.user.profile.languages.add(Language.objects.get(code="es"))
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Spanish")

    def test_view_component_guide(self):
        response = self.client.get(reverse("guide", kwargs=self.kw_component))
        self.assertContains(response, "Test/Test")

    def test_view_translation(self):
        response = self.client.get(self.translation.get_absolute_url())
        self.assertContains(response, "Test/Test")

    def test_view_translation_others(self):
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            other = Component.objects.create(
                name="RESX component",
                slug="resx",
                project=self.project,
                repo="weblate://test/test",
                file_format="resx",
                filemask="resx/*.resx",
                template="resx/en.resx",
                new_lang="add",
            )
        # Existing translation
        response = self.client.get(self.translation.get_absolute_url())
        self.assertContains(response, other.name)
        # Ghost translation
        kwargs = {"path": [*self.component.get_url_path(), "it"]}
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertContains(response, other.name)

    def test_view_redirect(self):
        """Test case insensitive lookups and aliases in middleware."""
        # Non existing fails with 404
        response = self.client.get(reverse("show", kwargs={"path": ["invalid"]}))
        self.assertEqual(response.status_code, 404)

        # Different casing should redirect, MySQL always does case insensitive lookups
        if using_postgresql():
            response = self.client.get(
                reverse("show", kwargs={"path": [self.project.slug.upper()]})
            )
            self.assertRedirects(
                response, self.project.get_absolute_url(), status_code=301
            )

        # Non existing fails with 404
        kwargs = {"path": [*self.project.get_url_path(), "invalid"]}
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertEqual(response.status_code, 404)

        # Different casing should redirect, MySQL always does case insensitive lookups
        kwargs["path"][-1] = self.component.slug.upper()
        if using_postgresql():
            response = self.client.get(reverse("show", kwargs=kwargs))
            self.assertRedirects(
                response,
                self.component.get_absolute_url(),
                status_code=301,
            )

        # Non existing fails with 404
        kwargs["path"][-1] = self.component.slug
        kwargs["path"].append("cs-DE")
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertEqual(response.status_code, 404)

        # Aliased language should redirect
        kwargs["path"][-1] = "czech"
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertRedirects(
            response,
            self.translation.get_absolute_url(),
            status_code=301,
        )

        # Non existing translated language should redirect with an info message
        kwargs["path"][-1] = "Hindi"
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertRedirects(
            response, self.component.get_absolute_url(), status_code=302
        )
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Hindi translation is currently not available", messages[0])

    def test_view_unit(self):
        unit = self.get_unit()
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, "Hello, world!")

    def test_view_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)
        response = self.client.get(reverse("component-list", kwargs={"name": "testcl"}))
        self.assertContains(response, "TestCL")
        self.assertContains(response, self.component.name)


class BasicMonolingualViewTest(BasicViewTest):
    def create_component(self):
        return self.create_po_mono()


class SourceStringsTest(ViewTestCase):
    def test_edit_priority(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_unit
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}),
            {"extra_flags": "priority:60"},
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertEqual(unit.priority, 60)

    def test_edit_readonly(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        unit = self.get_unit()
        old_state = unit.state
        source = unit.source_unit
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}),
            {"extra_flags": "read-only"},
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertTrue(unit.readonly)
        self.assertNotEqual(unit.state, old_state)

        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}), {"extra_flags": ""}
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertFalse(unit.readonly)
        self.assertEqual(unit.state, old_state)

    def test_edit_context(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_unit
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}),
            {"explanation": "Extra context"},
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit().source_unit
        self.assertEqual(unit.context, "")
        self.assertEqual(unit.explanation, "Extra context")

    def test_edit_check_flags(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_unit
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}),
            {"extra_flags": "ignore-same"},
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit().source_unit
        self.assertEqual(unit.extra_flags, "ignore-same")

    def test_view_source(self):
        kwargs = {"path": [*self.component.get_url_path(), "en"]}
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertContains(response, "Test/Test")

    def test_matrix(self):
        response = self.client.get(reverse("matrix", kwargs=self.kw_component))
        self.assertContains(response, "Czech")

    def test_matrix_load(self):
        response = self.client.get(
            reverse("matrix-load", kwargs=self.kw_component) + "?offset=0&lang=cs"
        )
        self.assertContains(response, 'lang="cs"')

    def test_toggle_flags(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_unit
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}), {"addflag": "read-only"}
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertIn("read-only", unit.all_flags)

        source = self.get_unit().source_unit
        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}), {"addflag": "read-only"}
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertIn("read-only", unit.all_flags)

        response = self.client.post(
            reverse("edit_context", kwargs={"pk": source.pk}),
            {"removeflag": "read-only"},
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertNotIn("read-only", unit.all_flags)
