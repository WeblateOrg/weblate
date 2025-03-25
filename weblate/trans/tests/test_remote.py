# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for changes done in remote repository."""

import os

from django.db import transaction
from django.test.utils import override_settings

from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import REPOWEB_URL
from weblate.utils.files import remove_tree
from weblate.utils.state import STATE_TRANSLATED
from weblate.vcs.models import VCS_REGISTRY

EXTRA_PO = """
#: accounts/models.py:319 trans/views/basic.py:104 weblate/html/index.html:21
msgid "Languages"
msgstr "Jazyky"
"""

MINIMAL_PO = r"""
msgid ""
msgstr ""
"Project-Id-Version: Weblate Hello World 2012\n"
"Report-Msgid-Bugs-To: <noreply@example.net>\n"
"POT-Creation-Date: 2012-03-14 15:54+0100\n"
"PO-Revision-Date: 2013-08-25 15:23+0200\n"
"Last-Translator: testuser <>\n"
"Language-Team: Czech <http://example.com/projects/test/test/cs/>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;\n"
"X-Generator: Weblate 1.7-dev\n"

#: main.c:11
#, c-format
msgid "Hello, world!\n"
msgstr "Nazdar svete!\n"
"""


class MultiRepoTest(ViewTestCase):
    """Test handling of remote changes, conflicts and so on."""

    _vcs = "git"
    _branch = "main"
    _filemask = "po/*.po"

    def setUp(self) -> None:
        super().setUp()
        if self._vcs not in VCS_REGISTRY:
            self.skipTest(f"VCS {self._vcs} not available!")
        repo = push = self.format_local_path(getattr(self, f"{self._vcs}_repo_path"))
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            self.component2 = Component.objects.create(
                name="Test 2",
                slug="test-2",
                project=self.project,
                repo=repo,
                push=push,
                vcs=self._vcs,
                filemask=self._filemask,
                template="",
                file_format="po",
                repoweb=REPOWEB_URL,
                new_base="",
                branch=self._branch,
            )
        self.request = self.get_request()

    def push_first(self, propagate=True, newtext="Nazdar svete!\n") -> None:
        """Change and pushes first component."""
        if not propagate:
            # Disable changes propagating
            self.component2.allow_translation_propagation = False
            self.component2.save()

        unit = self.get_unit()
        unit.translate(self.user, [newtext], STATE_TRANSLATED)
        self.assertEqual(self.get_translation().stats.translated, 1)
        self.component.do_push(self.request)

    def push_replace(self, content, mode) -> None:
        """Replace content of a po file and pushes it to remote repository."""
        # Manually edit po file, adding new unit
        translation = self.component.translation_set.get(language_code="cs")
        with open(translation.get_filename(), mode) as handle:
            handle.write(content)

        # Do changes in first repo
        with transaction.atomic():
            translation.git_commit(self.request.user, "TEST <test@example.net>")
        self.assertFalse(translation.needs_commit())
        translation.component.do_push(self.request)

    def test_propagate(self) -> None:
        """Test handling of propagating."""
        # Do changes in first repo
        self.push_first()

        # Verify changes got to the second one
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.translated, 1)

        # The text is intentionally duplicated to trigger check
        new_text = "Other text text\n"

        # Propagate edit
        unit = self.get_unit()
        self.assertEqual(len(unit.all_checks), 0)
        self.assertEqual(len(unit.propagated_units), 1)
        unit.translate(self.user, [new_text], STATE_TRANSLATED)

        # Verify new content
        unit = self.get_unit()
        self.assertEqual(unit.target, new_text)
        self.assertEqual(len(unit.propagated_units), 1)
        other_unit = unit.propagated_units[0]
        self.assertEqual(other_unit.target, new_text)

        # There should be no checks on both
        self.assertEqual(
            list(unit.check_set.values_list("name", flat=True)), ["duplicate"]
        )
        self.assertEqual(
            list(other_unit.check_set.values_list("name", flat=True)), ["duplicate"]
        )

    def test_failed_update(self) -> None:
        """Test failed remote update."""
        if os.path.exists(self.git_repo_path):
            remove_tree(self.git_repo_path)
        if os.path.exists(self.mercurial_repo_path):
            remove_tree(self.mercurial_repo_path)
        if os.path.exists(self.subversion_repo_path):
            remove_tree(self.subversion_repo_path)
        translation = self.component.translation_set.get(language_code="cs")
        self.assertFalse(translation.do_update(self.request))

    def test_update(self) -> None:
        """Test handling update in case remote has changed."""
        # Do changes in first repo
        self.push_first(False)

        # Test pull
        translation = self.component2.translation_set.get(language_code="cs")
        translation.invalidate_cache()
        self.assertEqual(translation.stats.translated, 0)

        translation.do_update(self.request)
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.translated, 1)

    def test_rebase(self) -> None:
        """Testing of rebase."""
        self.component2.merge_style = "rebase"
        self.component2.save()
        self.test_update()

    def test_conflict(self) -> None:
        """Test conflict handling."""
        # Do changes in first repo
        self.push_first(False)

        # Do changes in the second repo
        translation = self.component2.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, ["Ahoj svete!\n"], STATE_TRANSLATED)

        self.assertFalse(translation.do_update(self.request))

        self.assertFalse(translation.do_push(self.request))

    def test_more_changes(self) -> None:
        """Test more string changes in remote repo."""
        translation = self.component2.translation_set.get(language_code="cs")

        self.push_first(False, "Hello, world!\n")
        translation.do_update(self.request)
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.allchecks, 1)

        self.push_first(False, "Nazdar svete\n")
        translation.do_update(self.request)
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.allchecks, 0)

    def test_new_unit(self) -> None:
        """Test adding new unit with update."""
        self.push_replace(EXTRA_PO, "a")

        self.component2.do_update(self.request)

        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.all, 5)

    def test_deleted_unit(self) -> None:
        """Test removing several units from remote repo."""
        self.push_replace(MINIMAL_PO, "w")

        self.component2.do_update(self.request)

        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.all, 1)

    def test_deleted_stale_unit(self) -> None:
        """
        Test removing several units from remote repo.

        There is no other reference, so full cleanup has to happen.
        """
        self.push_replace(MINIMAL_PO, "w")
        self.component.delete()

        self.component2.do_update(self.request)

        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.all, 1)


class GitBranchMultiRepoTest(MultiRepoTest):
    _vcs = "git"
    _branch = "translations"
    _filemask = "translations/*.po"

    def create_component(self):
        return self.create_po_branch()


class MercurialMultiRepoTest(MultiRepoTest):
    _vcs = "mercurial"
    _branch = "default"

    def create_component(self):
        return self.create_po_mercurial()


class SubversionMultiRepoTest(MultiRepoTest):
    _vcs = "subversion"
    _branch = "master"

    def create_component(self):
        return self.create_po_svn()
