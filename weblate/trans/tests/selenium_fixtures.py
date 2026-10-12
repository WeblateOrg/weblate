# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Opt-in, committed fixtures for live-server screenshot tests."""

from __future__ import annotations

import shutil
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
from unittest import TestCase

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connection

from weblate.lang.models import Language
from weblate.trans.models import Project
from weblate.trans.tests.utils import clear_users_cache
from weblate.utils.files import remove_tree

if TYPE_CHECKING:
    from collections.abc import Callable


def reuse_demo_fixture[DemoTest: "ReusableSeleniumDemoMixin"](
    test: Callable[[DemoTest], None],
) -> Callable[[DemoTest], None]:
    """Restore the demo before the test body, leaving creation tests opt-out."""

    @wraps(test)
    def wrapped(self: DemoTest) -> None:
        self.set_up_demo_fixture()
        test(self)

    return wrapped


class ReusableSeleniumDemoMixin(TestCase):
    """
    Restore committed data rather than holding a live-server transaction open.

    Call before creating users or other test-specific data: restoration replaces
    the database. Only serialized data and repository paths survive between tests.
    Local GitHub transports remain per-test, including their configuration cleanup.
    """

    _demo_fixture_project_pk: int
    _demo_fixture_data: str
    _demo_fixture_repository: tuple[Path, Path]
    _demo_fixture_pk: int

    def use_github_fixtures(self) -> None:
        raise NotImplementedError

    def _build_demo_component(self) -> Project:
        raise NotImplementedError

    def set_up_demo_fixture(self) -> None:
        cls = type(self)
        Language.objects.flush_object_cache()
        clear_users_cache()
        cache.clear()
        self.use_github_fixtures()
        if "_demo_fixture_data" not in cls.__dict__:
            project = self._build_demo_component()
            snapshot = Path(
                cls.enterClassContext(
                    TemporaryDirectory(  # pylint: disable=consider-using-with
                        prefix="selenium-demo-", dir=settings.DATA_DIR
                    )
                )
            )
            path = Path(project.full_path)
            cls.addClassCleanup(remove_tree, path, True)
            saved = snapshot / "repository"
            shutil.copytree(path, saved, symlinks=True)
            data = connection.creation.serialize_db_to_string()
            cls._demo_fixture_data = data
            cls._demo_fixture_repository = (path, saved)
            cls._demo_fixture_pk = project.pk
        else:
            # The normal TransactionTestCase flush already populated baseline
            # rows. Replace those too, preserving all fixture foreign keys.
            call_command(
                "flush", verbosity=0, interactive=False, inhibit_post_migrate=True
            )
            connection.creation.deserialize_db_from_string(cls._demo_fixture_data)
            models = [
                model
                for model in apps.get_models()
                if model._meta.can_migrate(connection)  # ruff: ignore[private-member-access]
            ]
            with connection.cursor() as cursor:
                for sql in connection.ops.sequence_reset_sql(no_style(), models):
                    cursor.execute(sql)
            path, saved = cls._demo_fixture_repository
            remove_tree(path, True)
            shutil.copytree(saved, path, symlinks=True)
        self._demo_fixture_project_pk = cls._demo_fixture_pk
        # This manager cache survives cache.clear() and can retain primary keys
        # from the baseline rows recreated by TransactionTestCase's flush.
        ContentType.objects.clear_cache()

    def get_demo_fixture(self) -> Project:
        return Project.objects.get(pk=self._demo_fixture_project_pk)
