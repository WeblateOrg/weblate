# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for translation views."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse, urlsplit
from zipfile import ZipFile

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db import connection
from django.template.loader import render_to_string
from django.test.client import RequestFactory
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils.translation import activate
from openpyxl import load_workbook
from PIL import Image

from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import (
    Group,
    Permission,
    Role,
    TeamMembership,
    setup_project_groups,
)
from weblate.lang.models import Language
from weblate.trans.models import (
    Category,
    Component,
    ComponentLink,
    ComponentList,
    Project,
    WorkflowSetting,
)
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.utils import (
    clear_users_cache,
    create_another_user,
    create_test_user,
    wait_for_celery,
)
from weblate.utils.hash import hash_to_checksum
from weblate.utils.state import STATE_TRANSLATED
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.views import zip_download
from weblate.utils.xml import parse_xml

if TYPE_CHECKING:
    from django.test.client import Client as TestClient
    from django.test.client import _MonkeyPatchedWSGIResponse as TestClientResponse

    from weblate.auth.models import User
    from weblate.trans.models import Translation, Unit
    from weblate.utils.state import StringState


class PaginatorTemplateTest(TestCase):
    def test_anchor_in_page_form_action(self) -> None:
        page_obj = Paginator(range(11), 10).page(1)

        rendered = render_to_string(
            "paginator.html", {"page_obj": page_obj, "anchor": "components"}
        )

        self.assertIn('<form method="get" action="#components">', rendered)


class ZipDownloadTest(TestCase):
    def test_zip_download_rejects_symlink_to_other_allowed_root(self) -> None:
        sentinel = b"other component"

        with TemporaryDirectory() as root_name:
            root = Path(root_name)
            component = root / "component"
            other_component = root / "other-component"
            component.mkdir()
            other_component.mkdir()
            (component / "regular.txt").write_bytes(b"inside component")
            (component / "shared.txt").write_bytes(b"shared translation")
            (other_component / "secret.txt").write_bytes(sentinel)
            os.symlink(component / "shared.txt", component / "safe_link.txt")
            os.symlink(other_component / "secret.txt", component / "cross_link.txt")

            response = zip_download(
                str(root),
                [str(component)],
                allowed_roots=[str(component), str(other_component)],
            )

        with ZipFile(BytesIO(response.content), "r") as archive:
            self.assertIn("component/regular.txt", archive.namelist())
            self.assertEqual(
                archive.read("component/safe_link.txt"), b"shared translation"
            )
            self.assertNotIn("component/cross_link.txt", archive.namelist())
            archived_files = [archive.read(name) for name in archive.namelist()]

        self.assertFalse(any(sentinel in content for content in archived_files))

    def test_zip_download_validates_symlinked_file(self) -> None:
        sentinel = b"outside repository"

        with TemporaryDirectory() as root_name, TemporaryDirectory() as outside_name:
            root = Path(root_name)
            outside = Path(outside_name)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_bytes(b"repository metadata")
            (root / "build").mkdir()
            (root / "build" / "translation.txt").write_bytes(b"build directory")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "translation.txt").write_bytes(
                b"node_modules directory"
            )
            (root / "regular.txt").write_bytes(b"inside repository")
            (root / "shared.txt").write_bytes(b"shared translation")
            (outside / "secret.txt").write_bytes(sentinel)
            os.symlink(root / "shared.txt", root / "safe_link.txt")
            os.symlink(outside / "secret.txt", root / "leak_host.bin")
            os.symlink(root / "regular.txt", outside / "outside_link.txt")

            response = zip_download(
                str(root), [str(root), str(outside / "outside_link.txt")]
            )

        with ZipFile(BytesIO(response.content), "r") as archive:
            self.assertIn("regular.txt", archive.namelist())
            self.assertIn("build/translation.txt", archive.namelist())
            self.assertIn("node_modules/translation.txt", archive.namelist())
            self.assertEqual(archive.read("safe_link.txt"), b"shared translation")
            self.assertNotIn(".git/config", archive.namelist())
            self.assertNotIn("leak_host.bin", archive.namelist())
            self.assertFalse(any(name.startswith("../") for name in archive.namelist()))
            archived_files = [archive.read(name) for name in archive.namelist()]

        self.assertFalse(any(sentinel in content for content in archived_files))


class RegistrationTestMixin(TestCase):
    """Helper to share code for registration testing."""

    def assert_registration_mailbox(self, match: str | None = None) -> str:
        if match is None:
            match = "[Weblate] Your registration on Weblate"
        # Check mailbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, match)

        live_url = getattr(self, "live_server_url", None)

        # Parse URL
        url: str | None = None
        for line in mail.outbox[0].body.splitlines():
            if "verification_code" not in line:
                continue
            if "(" in line or ")" in line or "<" in line or ">" in line:
                continue
            if live_url and line.startswith(live_url):
                url = line
                break
            if line.startswith("http://example.com/"):
                url = line[18:]
                break

        self.assertIsNotNone(url, "Confirmation URL not found")
        return cast("str", url)

    def confirm_registration_url(
        self, url: str, client: TestClient | None = None, *, follow: bool = True
    ) -> TestClientResponse:
        client = client or self.client
        response = client.get(url, follow=follow)
        confirmation_template = "social_django/partial_pipeline_external_resume.html"
        if confirmation_template not in [
            template.name for template in response.templates
        ]:
            return response
        context = response.context
        return client.post(
            context["action_url"],
            {
                context["confirmation_parameter"]: context["confirmation_value"],
                context["confirmation_nonce_parameter"]: context["confirmation_nonce"],
            },
            follow=follow,
        )

    def assert_notify_mailbox(self, sent_mail) -> None:
        self.assertEqual(
            sent_mail.subject, "[Weblate] Activity on your account at Weblate"
        )

    def confirm_tos(
        self, user_client: TestClient, response: TestClientResponse
    ) -> TestClientResponse:
        url = response.redirect_chain[-1][0]
        parsed_url = urlparse(url)
        parsed_query = parse_qs(parsed_url.query)
        self.assertTrue(url.startswith(reverse("legal:confirm")))
        return user_client.post(
            url, {"confirm": "1", "next": parsed_query["next"]}, follow=True
        )


class ComponentTestCase(RepoTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        clear_users_cache()
        super().setUpTestData()

    def setUp(self) -> None:
        super().setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = create_test_user()
        group = Group.objects.get(name="Users")
        self.user.groups.add(group)
        # Create project to have some test base
        self.component = self.create_component()
        self.project = self.component.project
        if not self.project.defined_groups.exists():
            setup_project_groups(self, self.project)
        self.translation = self.get_translation()
        # Invalidate caches
        cache.clear()

    @property
    def kw_project(self):
        return {"project": self.project.slug}

    @property
    def kw_project_path(self):
        return {"path": self.project.get_url_path()}

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

    def tearDown(self) -> None:
        super().tearDown()
        # Reset to English language
        activate("en")

    def update_fulltext_index(self) -> None:
        wait_for_celery()

    def make_manager(self) -> None:
        """Make user a Manager."""
        # Sitewide privileges
        self.user.groups.add(Group.objects.get(name="Managers"))
        # Project privileges
        self.project.add_user(self.user, "Administration")

    def set_up_authenticated_view(self) -> None:
        self.anotheruser = create_another_user()
        self.user.groups.add(Group.objects.get(name="Users"))
        self.client.login(username="testuser", password="testpassword")

    def get_request(self, user=None):
        """Get fake request object."""
        request = self.factory.get("/")
        request.user = user or self.user
        request.session = "session"
        messages = FallbackStorage(request)
        # ruff: ignore[private-member-access]
        request._messages = messages
        return request

    def get_translation(self, language: str = "cs") -> Translation:
        return self.component.translation_set.get(language__code=language)

    def get_unit(
        self,
        source: str = "Hello, world!\n",
        language: str = "cs",
        translation: Translation | None = None,
    ) -> Unit:
        if translation is None:
            translation = self.get_translation(language)
        return translation.unit_set.get(source__startswith=source)

    def change_unit(
        self,
        target: str,
        source: str = "Hello, world!\n",
        language: str = "cs",
        translation: Translation | None = None,
        user: User | None = None,
        state: StringState = STATE_TRANSLATED,
    ) -> Unit:
        unit = self.get_unit(source, language, translation=translation)
        unit.translate(user or self.user, target, state)
        return unit

    def assert_redirects_offset(self, response, exp_path, exp_offset) -> None:
        """Assert that offset in response matches expected one."""
        self.assertEqual(response.status_code, 302)

        # We don't use all variables
        _scheme, _netloc, path, query, _fragment = urlsplit(response["Location"])

        self.assertEqual(path, exp_path)

        exp_offset = f"offset={exp_offset:d}"
        self.assertIn(exp_offset, query)

    def assert_png(self, response) -> None:
        """Check whether response contains valid PNG image."""
        # Check response status code
        self.assertEqual(response.status_code, 200)
        self.assert_png_data(response.content)

    def assert_png_data(self, content) -> None:
        """Check whether data is PNG image."""
        # Try to load PNG with PIL
        image = Image.open(BytesIO(content))
        self.assertEqual(image.format, "PNG")

    def assert_zip(self, response, filename: str | None = None):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        with ZipFile(BytesIO(response.content), "r") as zipfile:
            self.assertIsNone(zipfile.testzip())
            if filename is not None:
                self.assertIn(filename, zipfile.namelist())
                with zipfile.open(filename) as handle:
                    return handle.read()
            return None

    def assert_excel(self, response) -> None:
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            "; charset=utf-8",
        )
        load_workbook(BytesIO(response.content))

    def assert_svg(self, response) -> None:
        """Check whether response is a SVG image."""
        # Check response status code
        self.assertEqual(response.status_code, 200)
        tree = parse_xml(response.content)
        self.assertEqual(tree.tag, "{http://www.w3.org/2000/svg}svg")

    def assert_backend(
        self,
        expected_translated: int,
        language: str = "cs",
        translation: Translation | None = None,
    ) -> None:
        """Check that backend has correct data."""
        if translation is None:
            translation = self.get_translation(language)
        translation.commit_pending("test", None)
        store = translation.component.file_format_cls(
            translation.get_filename(),
            None,
            file_format_params=translation.component.file_format_params,
        )
        messages: set[int] = set()
        translated = 0

        for unit in store.content_units:
            id_hash = unit.id_hash
            self.assertNotIn(id_hash, messages, "Duplicate string in the backend file!")
            if unit.is_translated():
                translated += 1

        self.assertEqual(
            translated,
            expected_translated,
            f"Did not find expected number of translations ({translated} != {expected_translated}).",
        )

    def edit_unit(
        self,
        source: str,
        target: str,
        language: str = "cs",
        follow: bool = False,
        translation: Translation | None = None,
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

    def log_as_jane(self) -> None:
        self.client.login(username="jane", password="testpassword")


class ViewTestCase(ComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.set_up_authenticated_view()


class FixtureComponentTestCase(ComponentTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
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

        # Make sure anonymous cache is cleared
        clear_users_cache()

        super().setUpTestData()

    def clone_test_repos(self) -> None:
        return

    # pylint: disable=arguments-differ
    def create_project(self, name: str = "Test", slug: str = "test", **kwargs):
        project = Project.objects.all()[0]
        setup_project_groups(self, project)
        return project

    def create_component(self):
        component = self.create_project().component_set.all()[0]
        component.create_path()
        return component


class FixtureTestCase(FixtureComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.set_up_authenticated_view()


class TranslationManipulationTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.component.new_lang = "add"
        self.component.save()

    def create_component(self):
        return self.create_po_new_base()

    def test_model_add(self) -> None:
        self.assertTrue(
            self.component.add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )
        self.assertTrue(
            self.component.translation_set.filter(language_code="af").exists()
        )

    def test_model_add_duplicate(self) -> None:
        request = self.get_request()
        self.assertFalse(get_messages(request))
        self.assertIsNone(
            self.component.add_new_language(Language.objects.get(code="de"), request)
        )
        self.assertTrue(get_messages(request))

    def test_model_add_disabled(self) -> None:
        self.component.new_lang = "contact"
        self.component.save()
        self.assertFalse(
            self.component.add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )

    def test_model_add_superuser(self) -> None:
        self.component.new_lang = "contact"
        self.component.save()
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(
            self.component.add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )

    def test_remove(self) -> None:
        translation = self.component.translation_set.get(language_code="de")
        translation.remove(self.user)
        # Force scanning of the repository
        self.component.create_translations_immediate()
        self.assertFalse(
            self.component.translation_set.filter(language_code="de").exists()
        )


class ProjectLanguageAdditionTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # default test component is new_lang = "contact"
        self.components = {"contact": self.component}
        for new_lang in ["add", "none", "url"]:
            self.components[new_lang] = self.create_po_new_base(
                new_lang=new_lang,
                name=f"test-{new_lang}",
                project=self.project,
            )
        self.url = reverse("new-language", kwargs={"path": self.project.get_url_path()})
        self.obj = self.project

    def create_component(self):
        return self.create_po_new_base()

    def test_no_eligible_components(self) -> None:
        self.obj.component_set.update(new_lang="none")
        response = self.client.get(self.url, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())
        self.assertContains(
            response, "Language addition is not supported by any of the components."
        )

        response = self.client.get(self.url, {"lang": "af"}, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())
        self.assertContains(
            response, "Language addition is not supported by any of the components."
        )

        self.user.is_superuser = True
        self.user.save()

        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response, "Language addition is not supported by any of the components."
        )
        self.assertIn("form", response.context)

    def test_permission(self) -> None:
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.save(update_fields=["access_control"])
        response = self.client.get(self.url, follow=True)
        self.assertEqual(response.status_code, 403)

    def test_existing_language_excluded(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        for component in self.components.values():
            self.client.post(
                reverse("new-language", kwargs={"path": component.get_url_path()}),
                {"lang": "af"},
                follow=True,
            )
            self.assertTrue(
                component.translation_set.filter(language_code="af").exists()
            )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)
        codes = {c[0] for c in response.context["form"]["lang"].field.choices}
        self.assertNotIn("af", codes)

        response = self.client.post(self.url, {"lang": "af"}, follow=True)
        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in response.context["messages"]]
        self.assertCountEqual(
            messages,
            [
                "Please fix errors in the form.",
            ],
        )

    def test_view_add_language(self) -> None:
        self.assertTrue(
            all(
                not c.translation_set.filter(language_code="af").exists()
                for c in self.components.values()
            )
        )
        response = self.client.post(self.url, {"lang": "af"}, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())

        messages = [m.message for m in response.context["messages"]]
        self.assertCountEqual(
            messages,
            [
                "Language Afrikaans added to 1 component.",
                "Language Afrikaans requested for 1 component.",
            ],
        )
        for new_lang, component in self.components.items():
            lang_exists = component.translation_set.filter(language_code="af").exists()
            self.assertEqual(lang_exists, new_lang == "add")

    def test_view_add_duplicate_language(self) -> None:
        """Test adding a language that already exists in some components."""
        # Add the language to one component directly
        self.assertTrue(
            all(
                not c.translation_set.filter(language_code="af").exists()
                for c in self.components.values()
            )
        )

        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(
            self.components["contact"].add_new_language(
                Language.objects.get(code="af"), self.get_request()
            )
        )
        self.assertTrue(
            self.components["add"].add_new_language(
                Language.objects.get(code="pa"), self.get_request()
            )
        )
        self.user.is_superuser = False
        self.user.save()

        response = self.client.post(self.url, {"lang": "af"}, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())

        messages = [m.message for m in response.context["messages"]]
        self.assertCountEqual(
            messages,
            [
                "Language Afrikaans added to 1 component.",
            ],
        )

        response = self.client.post(self.url, {"lang": "pa"}, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())
        messages = [m.message for m in response.context["messages"]]
        self.assertCountEqual(
            messages,
            [
                "Language Punjabi requested for 1 component.",
                "Language Punjabi could not be added to 1 component. Please check the component's configuration.",
            ],
        )

    def test_view_add_language_superuser(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        self.assertTrue(
            all(
                not c.translation_set.filter(language_code="af").exists()
                for c in self.components.values()
            )
        )
        response = self.client.post(self.url, {"lang": "af"}, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())

        messages = [m.message for m in response.context["messages"]]
        self.assertCountEqual(
            messages,
            [
                "Language Afrikaans added to 4 components.",
            ],
        )

        for component in self.components.values():
            self.assertTrue(
                component.translation_set.filter(language_code="af").exists()
            )

    def test_category_override_new_lang_policy(self) -> None:
        self.project.new_lang = "none"
        self.project.save(update_fields=["new_lang"])
        category = Category.objects.create(
            name="Add category",
            slug="add-category",
            project=self.project,
            new_lang="add",
            inherit_new_lang=False,
        )
        component = self.create_po_new_base(
            new_lang="none",
            name="test-inherited-add",
            project=self.project,
        )
        component.category = category
        component.inherit_new_lang = True
        component.save(update_fields=["category", "inherit_new_lang"])

        eligible_ids = set(
            self.project.components_user_can_add_new_language(self.user).values_list(
                "pk", flat=True
            )
        )

        self.assertIn(component.pk, eligible_ids)

    def test_category_blocks_inherited_new_lang_policy(self) -> None:
        category = Category.objects.create(
            name="Disabled category",
            slug="disabled-category",
            project=self.project,
            new_lang="none",
            inherit_new_lang=False,
        )
        component = self.create_po_new_base(
            new_lang="add",
            name="test-inherited-none",
            project=self.project,
        )
        component.category = category
        component.inherit_new_lang = True
        component.save(update_fields=["category", "inherit_new_lang"])

        eligible_ids = set(
            self.project.components_user_can_add_new_language(self.user).values_list(
                "pk", flat=True
            )
        )

        self.assertNotIn(component.pk, eligible_ids)

    def test_shared_component_uses_own_inherited_new_lang_policy(self) -> None:
        project = self.create_project(name="Shared source", slug="shared-source")
        project.new_lang = "none"
        project.save(update_fields=["new_lang"])
        component = self.create_po_new_base(
            new_lang="add",
            name="test-shared-inherited-none",
            project=project,
        )
        component.inherit_new_lang = True
        component.save(update_fields=["inherit_new_lang"])
        component.links.add(self.project)

        eligible_ids = set(
            self.project.components_user_can_add_new_language(self.user).values_list(
                "pk", flat=True
            )
        )

        self.assertNotIn(component.pk, eligible_ids)


class CategoryLanguageAdditionTest(ProjectLanguageAdditionTest):
    def setUp(self) -> None:
        super().setUp()
        self.category = self.create_category(self.project)

        for component in self.components.values():
            component.category = self.category
            component.save(update_fields=["category"])

        self.url = reverse(
            "new-language", kwargs={"path": self.category.get_url_path()}
        )
        self.obj = self.category

    def test_category_add_no_extra_components(self):
        """Test that adding a language to a category does not add it to components not in the category."""
        # Create a component in the same project but outside the category
        outside_component = self.create_po_new_base(
            new_lang="add",
            name="test-outside",
            project=self.project,
        )
        self.assertIsNone(outside_component.category)

        self.user.is_superuser = True
        self.user.save()

        response = self.client.post(self.url, {"lang": "af"}, follow=True)
        self.assertRedirects(response, self.obj.get_absolute_url())

        for component in self.components.values():
            self.assertTrue(
                component.translation_set.filter(language_code="af").exists()
            )

        # Language should NOT have been added to the component outside the category
        self.assertFalse(
            outside_component.translation_set.filter(language_code="af").exists()
        )

    def test_child_category_override_new_lang_policy(self) -> None:
        self.category.new_lang = "none"
        self.category.inherit_new_lang = False
        self.category.save(update_fields=["new_lang", "inherit_new_lang"])
        child = Category.objects.create(
            name="Child add category",
            slug="child-add-category",
            project=self.project,
            category=self.category,
            new_lang="add",
            inherit_new_lang=False,
        )
        component = self.create_po_new_base(
            new_lang="none",
            name="test-child-inherited-add",
            project=self.project,
        )
        component.category = child
        component.inherit_new_lang = True
        component.save(update_fields=["category", "inherit_new_lang"])

        eligible_ids = set(
            self.category.components_user_can_add_new_language(self.user).values_list(
                "pk", flat=True
            )
        )

        self.assertIn(component.pk, eligible_ids)

    def test_child_category_blocks_inherited_new_lang_policy(self) -> None:
        self.category.new_lang = "add"
        self.category.inherit_new_lang = False
        self.category.save(update_fields=["new_lang", "inherit_new_lang"])
        child = Category.objects.create(
            name="Child disabled category",
            slug="child-disabled-category",
            project=self.project,
            category=self.category,
            new_lang="none",
            inherit_new_lang=False,
        )
        component = self.create_po_new_base(
            new_lang="add",
            name="test-child-inherited-none",
            project=self.project,
        )
        component.category = child
        component.inherit_new_lang = True
        component.save(update_fields=["category", "inherit_new_lang"])

        eligible_ids = set(
            self.category.components_user_can_add_new_language(self.user).values_list(
                "pk", flat=True
            )
        )

        self.assertNotIn(component.pk, eligible_ids)


class BasicViewTest(ViewTestCase):
    def assert_upload_placeholder(self, response, tab: str) -> None:
        self.assertContains(response, "Upload translation")
        self.assertContains(
            response, "Uploading translations at this level is not supported."
        )
        self.assertContains(response, f'data-bs-target="{tab}"')

    def assert_no_upload_placeholder(self, response) -> None:
        self.assertNotContains(response, "Upload translation")

    def test_view_project(self) -> None:
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "test/test")
        self.assertNotContains(response, "Spanish")

    def test_view_project_upload_placeholder(self) -> None:
        response = self.client.get(self.project.get_absolute_url())

        self.assert_upload_placeholder(response, "#languages")

    def test_upload_placeholder_for_membership_limited_translator(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save(update_fields=["category"])

        self.user.groups.clear()
        group = Group.objects.create(
            name="Limited upload", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        group.roles.add(Role.objects.get(name="Power user"))
        self.user.groups.add(group)
        membership = TeamMembership.objects.get(user=self.user, group=group)
        membership.limit_languages.set([self.translation.language])
        self.user.clear_permissions_cache()

        for url, tab in (
            (self.project.get_absolute_url(), "#languages"),
            (self.component.get_absolute_url(), "#translations"),
            (category.get_absolute_url(), "#languages"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assert_upload_placeholder(response, tab)

    def test_upload_placeholder_skips_children_without_upload_scope(self) -> None:
        self.user.groups.clear()
        group = Group.objects.create(
            name="Project access only", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        with patch(
            "weblate.auth.permissions._get_upload_child_translations"
        ) as get_upload_child_translations:
            response = self.client.get(self.project.get_absolute_url())

        self.assert_no_upload_placeholder(response)
        get_upload_child_translations.assert_not_called()

    def test_upload_placeholder_requires_uploadable_child_translation(self) -> None:
        project = self.create_project(
            name="Restricted upload", slug="restricted-upload"
        )
        category = self.create_category(project)
        self.create_po(
            project=project,
            category=category,
            name="restricted-upload",
            restricted=True,
        )

        self.user.groups.clear()
        group = Group.objects.create(
            name="Restricted project upload", language_selection=SELECTION_ALL
        )
        group.projects.add(project)
        group.roles.add(Role.objects.get(name="Power user"))
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        for url in (project.get_absolute_url(), category.get_absolute_url()):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assert_no_upload_placeholder(response)

    def test_upload_placeholder_uses_component_scoped_permissions(self) -> None:
        project = self.create_project(
            name="Component scoped upload", slug="component-scoped-upload"
        )
        category = self.create_category(project)
        component = self.create_po(
            project=project,
            category=category,
            name="restricted-component-upload",
            restricted=True,
        )
        translation = component.translation_set.get(language=self.translation.language)

        self.user.groups.clear()
        group = Group.objects.create(
            name="Component scoped upload", language_selection=SELECTION_ALL
        )
        group.components.add(component)
        group.roles.add(Role.objects.get(name="Power user"))
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        for url, tab in (
            (project.get_absolute_url(), "#languages"),
            (
                ProjectLanguage(project, translation.language).get_absolute_url(),
                "#components",
            ),
            (category.get_absolute_url(), "#languages"),
            (
                CategoryLanguage(category, translation.language).get_absolute_url(),
                "#components",
            ),
            (component.get_absolute_url(), "#translations"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assert_upload_placeholder(response, tab)

    def test_upload_placeholder_uses_component_link_category(self) -> None:
        source_project = self.create_project(
            name="Shared upload source", slug="shared-upload-source"
        )
        shared_component = self.create_po(
            project=source_project, name="shared-category-upload"
        )
        linked_category = Category.objects.create(
            name="Linked category",
            slug="linked-category",
            project=self.project,
        )
        unrelated_category = Category.objects.create(
            name="Unrelated category",
            slug="unrelated-category",
            project=self.project,
        )
        ComponentLink.objects.create(
            component=shared_component,
            project=self.project,
            category=linked_category,
        )

        self.user.groups.clear()
        access_group = Group.objects.create(
            name="Shared target access", language_selection=SELECTION_ALL
        )
        access_group.projects.add(self.project)
        upload_group = Group.objects.create(
            name="Shared component upload", language_selection=SELECTION_ALL
        )
        upload_group.components.add(shared_component)
        upload_group.roles.add(Role.objects.get(name="Power user"))
        self.user.groups.add(access_group, upload_group)
        self.user.clear_permissions_cache()

        response = self.client.get(linked_category.get_absolute_url())
        self.assert_upload_placeholder(response, "#languages")

        response = self.client.get(unrelated_category.get_absolute_url())
        self.assert_no_upload_placeholder(response)

    def test_view_project_preloads_workflow_settings(self) -> None:
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            translation_review=True,
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.project.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Czech")
        workflow_queries = [
            query for query in queries if '"trans_workflowsetting"' in query["sql"]
        ]
        self.assertLessEqual(
            len(workflow_queries),
            1,
            "\n".join(query["sql"] for query in workflow_queries),
        )

    def test_project_component_listing_shows_inherited_license_badge(self) -> None:
        self.project.license = "MIT"
        self.project.save(update_fields=["license"])
        self.component.license = ""
        self.component.inherit_license = True
        self.component.save(update_fields=["license", "inherit_license"])

        response = self.client.get(self.project.get_absolute_url())

        self.assertContains(response, 'class="license badge">MIT</span>')

    def test_view_project_deduplicates_outgoing_shared_component(self) -> None:
        first_project = Project.objects.create(name="Shared target one", slug="target1")
        second_project = Project.objects.create(
            name="Shared target two", slug="target2"
        )
        ComponentLink.objects.create(component=self.component, project=first_project)
        ComponentLink.objects.create(component=self.component, project=second_project)

        response = self.client.get(self.project.get_absolute_url())

        component_ids = [component.pk for component in response.context["components"]]
        self.assertEqual(component_ids.count(self.component.pk), 1)

    def test_view_project_ghost(self) -> None:
        self.user.profile.languages.add(Language.objects.get(code="es"))
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "Spanish")
        self.assertContains(response, '<input type="hidden" name="lang" value="es" />')

    def test_view_component(self) -> None:
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Test/Test")
        self.assertNotContains(response, "Spanish")

    def test_view_component_upload_placeholder(self) -> None:
        response = self.client.get(self.component.get_absolute_url())

        self.assert_upload_placeholder(response, "#translations")

    def test_glossary_component_upload_placeholder(self) -> None:
        category = self.create_category(self.project)
        self.component.create_glossary()
        glossary = Component.objects.get(project=self.project, is_glossary=True)
        glossary.category = category
        glossary.save(update_fields=["category"])
        glossary_translation = glossary.translation_set.exclude(
            language=glossary.source_language
        ).first()
        if glossary_translation is None:
            glossary_translation = glossary.translation_set.first()
        self.assertIsNotNone(glossary_translation)
        assert glossary_translation is not None
        language = glossary_translation.language

        self.user.groups.clear()
        group = Group.objects.create(
            name="Glossary upload", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        group.roles.add(Role.objects.get(name="Manage glossary"))
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

        for url, tab in (
            (self.project.get_absolute_url(), "#languages"),
            (
                ProjectLanguage(self.project, language).get_absolute_url(),
                "#components",
            ),
            (category.get_absolute_url(), "#languages"),
            (
                CategoryLanguage(category, language).get_absolute_url(),
                "#components",
            ),
            (glossary.get_absolute_url(), "#translations"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assert_upload_placeholder(response, tab)

    def test_view_component_ghost(self) -> None:
        self.user.profile.languages.add(Language.objects.get(code="es"))
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Spanish")
        self.assertContains(response, '<input type="hidden" name="lang" value="es" />')

    @override_settings(BASIC_LANGUAGES=set())
    def test_view_component_ghost_for_project_translation_language(self) -> None:
        language = Language.objects.get(code="fr")
        other = self.create_po_new_base(
            project=self.project,
            name="Other component",
            new_lang="add",
        )
        other.add_new_language(language, None, show_messages=False)

        self.user.profile.languages.add(language)
        response = self.client.get(self.component.get_absolute_url())

        self.assertContains(response, "French")
        self.assertContains(response, '<input type="hidden" name="lang" value="fr" />')

    @override_settings(BASIC_LANGUAGES=set())
    def test_view_component_ghost_for_project_source_language(self) -> None:
        language = Language.objects.get(code="fr")
        self.create_po_new_base(
            project=self.project,
            name="French source component",
            source_language=language,
            new_lang="add",
        )

        self.user.profile.languages.add(language)
        response = self.client.get(self.component.get_absolute_url())

        self.assertContains(response, "French")
        self.assertContains(response, '<input type="hidden" name="lang" value="fr" />')

    @override_settings(BASIC_LANGUAGES=set())
    def test_view_component_ghost_ignores_unrelated_language(self) -> None:
        language = Language.objects.auto_get_or_create("zz_ZZ")
        self.user.profile.languages.add(language)

        response = self.client.get(self.component.get_absolute_url())

        self.assertNotContains(
            response, '<input type="hidden" name="lang" value="zz_ZZ" />'
        )

    def test_view_component_guide(self) -> None:
        response = self.client.get(reverse("guide", kwargs=self.kw_component))
        self.assertRedirects(
            response, f"{self.component.get_absolute_url()}?alerts=1#alerts"
        )

    def test_view_translation(self) -> None:
        response = self.client.get(self.translation.get_absolute_url())
        self.assertContains(response, "Test/Test")

    def test_view_project_language_upload_placeholder(self) -> None:
        project_language = ProjectLanguage(self.project, self.translation.language)

        response = self.client.get(project_language.get_absolute_url())

        self.assert_upload_placeholder(response, "#components")

    def test_view_translation_others(self) -> None:
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

    def test_translate_other_occurrences_component_queries_do_not_scale(self) -> None:
        unit = self.get_unit()

        self.create_po(project=self.project, name="other-1")
        baseline_queries = self.count_translate_other_occurrence_relation_queries(unit)

        for index in range(2, 5):
            self.create_po(project=self.project, name=f"other-{index}")

        self.assertEqual(
            self.count_translate_other_occurrence_relation_queries(unit),
            baseline_queries,
        )

    def count_translate_other_occurrence_relation_queries(self, unit: Unit) -> int:
        session = self.client.session
        for key in list(session.keys()):
            if key.startswith("search_"):
                del session[key]
        session.save()

        response = self.client.get(
            unit.translation.get_translate_url(), {"checksum": unit.checksum}
        )
        self.assertContains(response, "Other occurrences")

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                unit.translation.get_translate_url(), {"checksum": unit.checksum}
            )

        self.assertContains(response, "Other occurrences")

        return sum(
            (
                'FROM "trans_component"' in query["sql"]
                and 'WHERE "trans_component"."id" =' in query["sql"]
            )
            or (
                'FROM "trans_project"' in query["sql"]
                and 'WHERE "trans_project"."id" =' in query["sql"]
            )
            for query in queries
        )

    def test_view_unit(self) -> None:
        unit = self.get_unit()
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, "Hello, world!")

    def test_view_component_list(self) -> None:
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)
        response = self.client.get(reverse("component-list", kwargs={"name": "testcl"}))
        self.assertContains(response, "TestCL")
        self.assertContains(response, self.component.name)

    def test_view_empty_component_list_denied(self) -> None:
        ComponentList.objects.create(name="TestCL", slug="testcl")

        response = self.client.get(reverse("component-list", kwargs={"name": "testcl"}))

        self.assertEqual(response.status_code, 404)

    def test_view_restricted_component_list_denied(self) -> None:
        restricted_component = self.create_po(
            project=self.project, name="Restricted", restricted=True
        )
        clist = ComponentList.objects.create(name="RestrictedCL", slug="restrictedcl")
        clist.components.add(restricted_component)

        response = self.client.get(
            reverse("component-list", kwargs={"name": "restrictedcl"})
        )

        self.assertEqual(response.status_code, 404)

    def test_view_empty_component_list_with_management_permission(self) -> None:
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.autocomponentlist_set.create(
            project_match="^internal-", component_match="^.*$"
        )
        group = Group.objects.create(
            name="Component list managers", language_selection=SELECTION_ALL
        )
        role = Role.objects.create(name="Component list management")
        role.permissions.add(Permission.objects.get(codename="componentlist.edit"))
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.client.login(username="testuser", password="testpassword")

        response = self.client.get(reverse("component-list", kwargs={"name": "testcl"}))

        self.assertContains(response, "TestCL")

    def test_view_private_component_list_with_management_permission(self) -> None:
        private_project = self.create_project(
            name="Private", slug="private", access_control=Project.ACCESS_PRIVATE
        )
        private_component = self.create_po(project=private_project, name="Private")
        clist = ComponentList.objects.create(name="PrivateCL", slug="privatecl")
        clist.components.add(private_component)
        group = Group.objects.create(
            name="Component list managers", language_selection=SELECTION_ALL
        )
        role = Role.objects.create(name="Component list management")
        role.permissions.add(Permission.objects.get(codename="componentlist.edit"))
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.client.login(username="testuser", password="testpassword")

        response = self.client.get(
            reverse("component-list", kwargs={"name": "privatecl"})
        )

        self.assertContains(response, "PrivateCL")

    def test_view_category(self) -> None:
        category = self.create_category(self.project)
        cat_component = self.create_po(
            project=self.project, category=category, name="Category Component"
        )
        response = self.client.get(category.get_absolute_url())
        self.assertContains(response, category.name)
        self.assertContains(response, cat_component.name)
        self.assertNotContains(response, "Spanish")

        self.user.profile.languages.add(Language.objects.get(code="es"))
        response = self.client.get(category.get_absolute_url())
        self.assertContains(response, category.name)
        self.assertContains(response, cat_component.name)
        self.assertContains(response, "Spanish")

    def test_view_category_upload_placeholder(self) -> None:
        category = self.create_category(self.project)
        self.create_po(
            project=self.project, category=category, name="Category Component"
        )

        response = self.client.get(category.get_absolute_url())

        self.assert_upload_placeholder(response, "#languages")

    def test_view_category_language_upload_placeholder(self) -> None:
        category = self.create_category(self.project)
        self.create_po(
            project=self.project, category=category, name="Category Component"
        )
        category_language = CategoryLanguage(category, self.translation.language)

        response = self.client.get(category_language.get_absolute_url())

        self.assert_upload_placeholder(response, "#components")

    def test_category_language_upload_placeholder_respects_suggestions(self) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save(update_fields=["category"])

        self.user.groups.clear()
        role = Role.objects.create(name="Upload suggestions")
        role.permissions.add(
            Permission.objects.get(codename="suggestion.add"),
            Permission.objects.get(codename="upload.perform"),
        )
        group = Group.objects.create(
            name="Upload suggestions", language_selection=SELECTION_ALL
        )
        group.projects.add(self.project)
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        category_language = CategoryLanguage(category, self.translation.language)

        response = self.client.get(category_language.get_absolute_url())

        self.assert_upload_placeholder(response, "#components")

        self.component.enable_suggestions = False
        self.component.save(update_fields=["enable_suggestions"])
        self.user.clear_permissions_cache()
        category_language = CategoryLanguage(category, self.translation.language)

        response = self.client.get(category_language.get_absolute_url())

        self.assert_no_upload_placeholder(response)

        self.component.enable_suggestions = True
        self.component.save(update_fields=["enable_suggestions"])
        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            enable_suggestions=False,
        )
        self.user.clear_permissions_cache()
        category_language = CategoryLanguage(category, self.translation.language)

        response = self.client.get(category_language.get_absolute_url())

        self.assertNotContains(response, "Upload translation")


class BasicMonolingualViewTest(BasicViewTest):
    def create_component(self):
        return self.create_po_mono()


class SourceStringsTest(ViewTestCase):
    def test_edit_priority(self) -> None:
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

    def test_edit_readonly(self) -> None:
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

    def test_edit_context(self) -> None:
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

    def test_edit_context_hides_private_unit(self) -> None:
        private_project = self.create_project(
            name="Private source",
            slug="private-source",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="private-source"
        )
        private_translation = private_component.translation_set.get(language_code="cs")
        unit = self.get_unit(translation=private_translation).source_unit

        response = self.client.post(
            reverse("edit_context", kwargs={"pk": unit.pk}),
            {"explanation": "Extra context"},
        )
        self.assertEqual(response.status_code, 404)

    def test_edit_check_flags(self) -> None:
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

    def test_view_source(self) -> None:
        kwargs = {"path": [*self.component.get_url_path(), "en"]}
        response = self.client.get(reverse("show", kwargs=kwargs))
        self.assertContains(response, "Test/Test")

    def test_matrix(self) -> None:
        response = self.client.get(reverse("matrix", kwargs=self.kw_component))
        self.assertContains(response, "Czech")

    def test_matrix_load(self) -> None:
        response = self.client.get(
            f"{reverse('matrix-load', kwargs=self.kw_component)}?offset=0&lang=cs"
        )
        self.assertContains(response, 'lang="cs"')

    def test_toggle_flags(self) -> None:
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
