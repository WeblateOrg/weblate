# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for component guide suggestions."""

import os
import shutil
from pathlib import Path

from django.utils.functional import cached_property

from weblate.trans.guide import (
    DjangoGuideline,
    MesonGuideline,
    SphinxGuideline,
    XgettextGuideline,
)
from weblate.trans.tests.test_views import ViewTestCase


class ExtractorGuideTest(ViewTestCase):
    @cached_property
    def git_repo_path(self) -> str:
        path = self.get_repo_path("test-guide-repo.git")
        if os.path.exists(path):
            shutil.rmtree(path)
        shutil.copytree(self.git_base_repo_path, path)
        return path

    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_xgettext_guideline(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        guideline = XgettextGuideline(self.component)

        self.assertTrue(guideline.is_relevant())

    def test_django_guideline(self) -> None:
        self.component.new_base = "locale/django.pot"
        self.component.save(update_fields=["new_base"])

        guideline = DjangoGuideline(self.component)

        self.assertTrue(guideline.is_relevant())

    def test_sphinx_guideline(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        self.component.save(update_fields=["new_base"])
        docs_dir = Path(self.component.full_path) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "conf.py").write_text("extensions = []\n", encoding="utf-8")
        (docs_dir / "index.rst").write_text("Heading\n=======\n", encoding="utf-8")

        guideline = SphinxGuideline(self.component)

        self.assertTrue(guideline.is_relevant())

    def test_meson_guideline(self) -> None:
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")

        guideline = MesonGuideline(self.component)

        self.assertTrue(guideline.is_relevant())
