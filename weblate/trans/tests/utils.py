# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os.path
import shutil
import sys
from datetime import timedelta
from tarfile import TarFile
from tempfile import mkdtemp

import social_core.backends.utils
from celery.contrib.testing.tasks import ping  # type: ignore[import-untyped]
from celery.result import allow_join_result
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.test.utils import modify_settings, override_settings
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.auth.models import User
from weblate.configuration.models import Setting, SettingCategory
from weblate.formats.models import FILE_FORMATS
from weblate.trans.models import Category, Component, Project
from weblate.utils.files import remove_tree
from weblate.vcs.models import VCS_REGISTRY

# Directory holding test data
TEST_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

REPOWEB_URL = "https://nonexisting.weblate.org/blob/main/{{filename}}#L{{line}}"

TESTPASSWORD = make_password("testpassword")


def wait_for_celery(timeout=10) -> None:
    with allow_join_result():
        ping.delay().get(timeout=timeout)


def get_test_file(name):
    """Return filename of test file."""
    return os.path.join(TEST_DATA, name)


def create_test_user():
    return User.objects.create(
        username="testuser",
        email="weblate@example.org",
        password=TESTPASSWORD,
        full_name="Weblate Test",
    )


def create_another_user():
    return User.objects.create(
        username="jane",
        email="jane.doe@example.org",
        password=TESTPASSWORD,
        full_name="Jane Doe",
    )


class RepoTestMixin:
    """Mixin for testing with test repositories."""

    updated_base_repos: set[str] = set()
    CREATE_GLOSSARIES: bool = False

    local_repo_path = "local:"

    def optional_extract(self, output, tarname) -> None:
        """
        Extract test repository data if needed.

        Checks whether directory exists or is older than archive.
        """
        tarname = get_test_file(tarname)

        if not os.path.exists(output) or os.path.getmtime(output) < os.path.getmtime(
            tarname
        ):
            # Remove directory if outdated
            if os.path.exists(output):
                remove_tree(output)

            # Extract new content
            tar = TarFile(tarname)
            tar.extractall(settings.DATA_DIR)  # noqa: S202
            tar.close()

            # Update directory timestamp
            os.utime(output, None)
        self.updated_base_repos.add(output)

    @staticmethod
    def get_repo_path(name):
        return os.path.join(settings.DATA_DIR, name)

    @property
    def git_base_repo_path(self):
        path = self.get_repo_path("test-base-repo.git")
        if path not in self.updated_base_repos:
            self.optional_extract(path, "test-base-repo.git.tar")
        return path

    @cached_property
    def git_repo_path(self):
        path = self.get_repo_path("test-repo.git")
        shutil.copytree(self.git_base_repo_path, path)
        return path

    @property
    def mercurial_base_repo_path(self):
        path = self.get_repo_path("test-base-repo.hg")
        if path not in self.updated_base_repos:
            self.optional_extract(path, "test-base-repo.hg.tar")
        return path

    @cached_property
    def mercurial_repo_path(self):
        path = self.get_repo_path("test-repo.hg")
        shutil.copytree(self.mercurial_base_repo_path, path)
        return path

    @property
    def subversion_base_repo_path(self):
        path = self.get_repo_path("test-base-repo.svn")
        if path not in self.updated_base_repos:
            self.optional_extract(path, "test-base-repo.svn.tar")
        return path

    @cached_property
    def subversion_repo_path(self):
        path = self.get_repo_path("test-repo.svn")
        shutil.copytree(self.subversion_base_repo_path, path)
        return path

    def clone_test_repos(self) -> None:
        dirs = ["test-repo.git", "test-repo.hg", "test-repo.svn"]
        # Remove possibly existing directories
        for name in dirs:
            path = self.get_repo_path(name)
            if os.path.exists(path):
                remove_tree(path)

        # Remove cached paths
        keys = ["git_repo_path", "mercurial_repo_path", "subversion_repo_path"]
        for key in keys:
            if key in self.__dict__:
                del self.__dict__[key]

        # Remove possibly existing project directories
        test_repo_path = os.path.join(settings.DATA_DIR, "vcs")
        if os.path.exists(test_repo_path):
            remove_tree(test_repo_path)
        os.makedirs(test_repo_path)

    def create_project(self, name: str = "Test", slug: str = "test", **kwargs):
        """Create test project."""
        project = Project.objects.create(
            name=name, slug=slug, web="https://nonexisting.weblate.org/", **kwargs
        )
        self.addCleanup(remove_tree, project.full_path, True)
        return project

    def create_category(self, project, **kwargs):
        """Create test category."""
        return Category.objects.create(
            name="Test category", slug="test-category", project=project, **kwargs
        )

    def format_local_path(self, path):
        """Format path for local access to the repository."""
        if sys.platform != "win32":
            return f"file://{path}"
        return "file:///{}".format(path.replace("\\", "/"))

    def _create_component(
        self,
        file_format,
        mask,
        template="",
        new_base="",
        vcs="git",
        branch=None,
        **kwargs,
    ):
        """Create real test component."""
        if file_format not in FILE_FORMATS:
            self.skipTest(f"File format {file_format} is not supported!")
        if "project" not in kwargs:
            kwargs["project"] = self.create_project()

        repo = push = self.format_local_path(getattr(self, f"{vcs}_repo_path"))
        if vcs not in VCS_REGISTRY:
            self.skipTest(f"VCS {vcs} not available!")

        if "new_lang" not in kwargs:
            kwargs["new_lang"] = "contact"

        if "push_on_commit" not in kwargs:
            kwargs["push_on_commit"] = False

        if "name" not in kwargs:
            kwargs["name"] = "Test"
        kwargs["slug"] = kwargs["name"].lower()

        if "manage_units" not in kwargs and template:
            kwargs["manage_units"] = True

        if branch is None:
            if repo.startswith("weblate://"):
                branch = ""
            elif vcs == "subversion":
                branch = "master"
            else:
                branch = VCS_REGISTRY[vcs].get_remote_branch(repo)

        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            return Component.objects.create(
                repo=repo,
                push=push,
                branch=branch,
                filemask=mask,
                template=template,
                file_format=file_format,
                repoweb=REPOWEB_URL,
                new_base=new_base,
                vcs=vcs,
                **kwargs,
            )

    @staticmethod
    def configure_mt() -> None:
        for engine in ["weblate", "weblate-translation-memory"]:
            Setting.objects.get_or_create(
                category=SettingCategory.MT,
                name=engine,
                defaults={"value": {}},
            )

    def create_component(self):
        """Create test component."""
        return self.create_po()

    def create_po(self, **kwargs):
        return self._create_component("po", "po/*.po", **kwargs)

    def create_po_branch(self):
        return self._create_component("po", "translations/*.po", branch="translations")

    def create_po_push(self):
        return self.create_po(push_on_commit=True)

    def create_po_empty(self, project=None):
        kwargs = {"new_base": "po-empty/hello.pot", "new_lang": "add"}
        if project:
            kwargs["project"] = project

        return self._create_component("po", "po-empty/*.po", **kwargs)

    def create_po_mercurial(self):
        return self.create_po(vcs="mercurial")

    def create_po_mercurial_branch(self):
        return self._create_component(
            "po", "translations/*.po", branch="translations", vcs="mercurial"
        )

    def create_po_svn(self):
        return self.create_po(vcs="subversion")

    def create_po_new_base(self, **kwargs):
        return self.create_po(new_base="po/hello.pot", **kwargs)

    def create_po_link(self):
        return self._create_component("po", "po-link/*.po")

    def create_po_mono(self, **kwargs):
        return self._create_component(
            "po-mono", "po-mono/*.po", "po-mono/en.po", **kwargs
        )

    def create_srt(self):
        return self._create_component("srt", "srt/*.srt", "srt/en.srt")

    def create_ts(self, suffix="", **kwargs):
        return self._create_component("ts", f"ts{suffix}/*.ts", **kwargs)

    def create_ts_mono(self):
        return self._create_component("ts", "ts-mono/*.ts", "ts-mono/en.ts")

    def create_iphone(self, **kwargs):
        return self._create_component(
            "strings", "iphone/*.lproj/Localizable.strings", **kwargs
        )

    def create_android(self, suffix="", **kwargs):
        return self._create_component(
            "aresource",
            f"android{suffix}/values-*/strings.xml",
            f"android{suffix}/values/strings.xml",
            **kwargs,
        )

    def create_json(self):
        return self._create_component("json", "json/*.json")

    def create_json_mono(self, suffix="mono", **kwargs):
        return self._create_component(
            "json", f"json-{suffix}/*.json", f"json-{suffix}/en.json", **kwargs
        )

    def create_json_webextension(self):
        return self._create_component(
            "webextension",
            "webextension/_locales/*/messages.json",
            "webextension/_locales/en/messages.json",
        )

    def create_json_intermediate(self, **kwargs):
        return self._create_component(
            "json",
            "intermediate/*.json",
            "intermediate/en.json",
            intermediate="intermediate/dev.json",
            **kwargs,
        )

    def create_json_intermediate_empty(self, **kwargs):
        return self._create_component(
            "json",
            "intermediate/lang-*.json",
            "intermediate/lang-en.json",
            intermediate="intermediate/dev.json",
            **kwargs,
        )

    def create_joomla(self):
        return self._create_component("joomla", "joomla/*.ini", "joomla/en-GB.ini")

    def create_ini(self):
        return self._create_component("ini", "ini/*.ini", "ini/en.ini")

    def create_tsv(self):
        return self._create_component("csv", "tsv/*.txt")

    def create_csv(self):
        return self._create_component("csv", "csv/*.txt")

    def create_csv_mono(self):
        return self._create_component("csv", "csv-mono/*.csv", "csv-mono/en.csv")

    def create_php_mono(self):
        return self._create_component("php", "php-mono/*.php", "php-mono/en.php")

    def create_java(self):
        return self._create_component(
            "properties",
            "java/swing_messages_*.properties",
            "java/swing_messages.properties",
        )

    def create_xliff(self, name="default", **kwargs):
        return self._create_component("xliff", f"xliff/*/{name}.xlf", **kwargs)

    def create_xliff_mono(self):
        return self._create_component("xliff", "xliff-mono/*.xlf", "xliff-mono/en.xlf")

    def create_resx(self):
        return self._create_component("resx", "resx/*.resx", "resx/en.resx")

    def create_yaml(self):
        return self._create_component("yaml", "yml/*.yml", "yml/en.yml")

    def create_ruby_yaml(self):
        return self._create_component("ruby-yaml", "ruby-yml/*.yml", "ruby-yml/en.yml")

    def create_dtd(self):
        return self._create_component("dtd", "dtd/*.dtd", "dtd/en.dtd")

    def create_appstore(self):
        return self._create_component("appstore", "metadata/*", "metadata/en-US")

    def create_html(self):
        return self._create_component(
            "html", "html/*.html", "html/en.html", edit_template=False
        )

    def create_idml(self):
        return self._create_component(
            "idml", "idml/*.idml", "idml/en.idml", edit_template=False
        )

    def create_odt(self):
        return self._create_component(
            "odf", "odt/*.odt", "odt/en.odt", edit_template=False
        )

    def create_winrc(self):
        return self._create_component(
            "rc", "winrc/*.rc", "winrc/en-US.rc", edit_template=False
        )

    def create_tbx(self):
        return self._create_component("tbx", "tbx/*.tbx")

    def create_link(self, **kwargs):
        parent = self.create_iphone(*kwargs)
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            return Component.objects.create(
                name="Test2",
                slug="test2",
                project=parent.project,
                repo="weblate://test/test",
                file_format="po",
                filemask="po/*.po",
                new_lang="contact",
            )

    def create_link_existing(self):
        component = self.component
        if "linked_childs" in component.__dict__:
            del component.__dict__["linked_childs"]
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            return Component.objects.create(
                name="Test2",
                slug="test2",
                project=self.project,
                repo=component.get_repo_link_url(),
                file_format="po",
                filemask="po-duplicates/*.dpo",
                new_lang="contact",
            )


class TempDirMixin:
    _tempdir: str | None = None

    @property
    def tempdir(self) -> str:
        if self._tempdir is None:
            msg = "tempdir not initialized"
            raise ValueError(msg)
        return self._tempdir

    def create_temp(self) -> None:
        self._tempdir = mkdtemp(suffix="weblate")

    def remove_temp(self) -> None:
        if self._tempdir:
            remove_tree(self._tempdir)
            self._tempdir = None


def create_test_billing(user: User, invoice=True):
    from weblate.billing.models import Billing, Invoice, Plan

    plan = Plan.objects.create(
        limit_projects=1,
        display_limit_projects=1,
        name="Basic plan",
        price=19,
        yearly_price=199,
    )
    billing = Billing.objects.create(plan=plan)
    billing.owners.add(user)
    if invoice:
        Invoice.objects.create(
            billing=billing,
            amount=19,
            start=timezone.now() - timedelta(days=1),
            end=timezone.now() + timedelta(days=1),
        )
    return billing


class SocialCacheMixin:
    """
    Safely changes AUTHENTICATION_BACKENDS.

    Purge social_core authentication backends cache needs to be done upon any
    change to AUTHENTICATION_BACKENDS.
    """

    def enable(self) -> None:
        super().enable()
        social_core.backends.utils.BACKENDSCACHE = {}

    def disable(self) -> None:
        super().disable()
        social_core.backends.utils.BACKENDSCACHE = {}


# Lowercase name to be consistent with Django
class social_core_override_settings(SocialCacheMixin, override_settings):  # noqa: N801
    pass


# Lowercase name to be consistent with Django
class social_core_modify_settings(SocialCacheMixin, modify_settings):  # noqa: N801
    pass
