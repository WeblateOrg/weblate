#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
"""Test for changes done in remote repository."""
import os
from unittest import SkipTest

from django.db import transaction

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

    def setUp(self):
        super().setUp()
        if self._vcs not in VCS_REGISTRY:
            raise SkipTest(f"VCS {self._vcs} not available!")
        repo = push = self.format_local_path(getattr(self, f"{self._vcs}_repo_path"))
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

    def push_first(self, propagate=True, newtext="Nazdar svete!\n"):
        """Change and pushes first component."""
        if not propagate:
            # Disable changes propagating
            self.component2.allow_translation_propagation = False
            self.component2.save()

        unit = self.get_unit()
        unit.translate(self.user, [newtext], STATE_TRANSLATED)
        self.assertEqual(self.get_translation().stats.translated, 1)
        self.component.do_push(self.request)

    def push_replace(self, content, mode):
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

    def test_propagate(self):
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
        self.assertEqual(len(unit.same_source_units), 1)
        unit.translate(self.user, [new_text], STATE_TRANSLATED)

        # Verify new content
        unit = self.get_unit()
        self.assertEqual(unit.target, new_text)
        self.assertEqual(len(unit.same_source_units), 1)
        other_unit = unit.same_source_units[0]
        self.assertEqual(other_unit.target, new_text)

        # There should be no checks on both
        self.assertEqual(
            list(unit.check_set.values_list("check", flat=True)), ["duplicate"]
        )
        self.assertEqual(
            list(other_unit.check_set.values_list("check", flat=True)), ["duplicate"]
        )

    def test_failed_update(self):
        """Test failed remote update."""
        if os.path.exists(self.git_repo_path):
            remove_tree(self.git_repo_path)
        if os.path.exists(self.mercurial_repo_path):
            remove_tree(self.mercurial_repo_path)
        if os.path.exists(self.subversion_repo_path):
            remove_tree(self.subversion_repo_path)
        translation = self.component.translation_set.get(language_code="cs")
        self.assertFalse(translation.do_update(self.request))

    def test_update(self):
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

    def test_rebase(self):
        """Testing of rebase."""
        self.component2.merge_style = "rebase"
        self.component2.save()
        self.test_update()

    def test_conflict(self):
        """Test conflict handling."""
        # Do changes in first repo
        self.push_first(False)

        # Do changes in the second repo
        translation = self.component2.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, ["Ahoj svete!\n"], STATE_TRANSLATED)

        self.assertFalse(translation.do_update(self.request))

        self.assertFalse(translation.do_push(self.request))

    def test_more_changes(self):
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

    def test_new_unit(self):
        """Test adding new unit with update."""
        self.push_replace(EXTRA_PO, "a")

        self.component2.do_update(self.request)

        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.all, 5)

    def test_deleted_unit(self):
        """Test removing several units from remote repo."""
        self.push_replace(MINIMAL_PO, "w")

        self.component2.do_update(self.request)

        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(translation.stats.all, 1)

    def test_deleted_stale_unit(self):
        """Test removing several units from remote repo.

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
