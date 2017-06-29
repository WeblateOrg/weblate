# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

"""Test for translation views."""

from __future__ import unicode_literals
import time

from django.core.urlresolvers import reverse

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models import Change


class EditTest(ViewTestCase):
    """Test for manipulating translation."""
    has_plurals = True
    monolingual = False

    def setUp(self):
        super(EditTest, self).setUp()
        self.translation = self.get_translation()
        self.translate_url = reverse('translate', kwargs=self.kw_translation)

    def test_edit(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assert_backend(1)

        # Test that second edit with no change does not break anything
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assert_backend(1)

        # Test that third edit still works
        response = self.edit_unit(
            'Hello, world!\n',
            'Ahoj svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Ahoj svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assert_backend(1)

    def test_plurals(self):
        """Test plural editing."""
        if not self.has_plurals:
            return

        response = self.edit_unit(
            'Orangutan',
            'Opice má %d banán.\n',
            target_1='Opice má %d banány.\n',
            target_2='Opice má %d banánů.\n',
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        # Check translations
        unit = self.get_unit('Orangutan')
        plurals = unit.get_target_plurals()
        self.assertEqual(len(plurals), 3)
        self.assertEqual(
            plurals[0],
            'Opice má %d banán.\n',
        )
        self.assertEqual(
            plurals[1],
            'Opice má %d banány.\n',
        )
        self.assertEqual(
            plurals[2],
            'Opice má %d banánů.\n',
        )

    def test_fuzzy(self):
        """Test for fuzzy flag handling."""
        unit = self.get_unit()
        self.assertFalse(unit.fuzzy)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            fuzzy='yes'
        )
        unit = self.get_unit()
        self.assertTrue(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
        )
        unit = self.get_unit()
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            fuzzy='yes'
        )
        unit = self.get_unit()
        self.assertTrue(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)

    def test_skip_fuzzy(self):
        """Test for fuzzy flag handling."""
        if self.monolingual:
            return
        unit = self.get_unit()
        self.assertFalse(unit.fuzzy)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            fuzzy='yes'
        )
        unit = self.get_unit()
        self.assertTrue(unit.fuzzy)
        self.subproject.check_flags = 'skip-review-flag'
        self.subproject.save()
        self.subproject.create_translations(True)
        unit = self.get_unit()
        self.assertFalse(unit.fuzzy)
        self.subproject.check_flags = ''
        self.subproject.save()
        self.subproject.create_translations(True)
        unit = self.get_unit()
        self.assertTrue(unit.fuzzy)


class EditValidationTest(ViewTestCase):
    def edit(self, **kwargs):
        """Editing with no specific params."""
        unit = self.get_unit()
        params = {'checksum': unit.checksum}
        params.update(kwargs)
        return self.client.post(
            unit.translation.get_translate_url(),
            params,
            follow=True
        )

    def test_edit_invalid(self):
        """Editing with invalid params."""
        response = self.edit()
        self.assertContains(response, 'Missing translated string!')

    def test_suggest_invalid(self):
        """Suggesting with invalid params."""
        response = self.edit(suggest='1')
        self.assertContains(response, 'Missing translated string!')

    def test_edit_spam(self):
        """Editing with spam trap."""
        response = self.edit(content='1')
        self.assertContains(response, 'po/cs.po, translation unit 2')

    def test_merge(self):
        """Merging with invalid parameter."""
        unit = self.get_unit()
        response = self.client.get(
            unit.translation.get_translate_url(),
            {'checksum': unit.checksum, 'merge': 'invalid'},
            follow=True,
        )
        self.assertContains(response, 'Invalid merge request!')

    def test_merge_lang(self):
        """Merging across langauges."""
        unit = self.get_unit()
        trans = self.subproject.translation_set.exclude(
            language_code='cs'
        )[0]
        other = trans.unit_set.get(content_hash=unit.content_hash)
        response = self.client.get(
            unit.translation.get_translate_url(),
            {'checksum': unit.checksum, 'merge': other.pk},
            follow=True,
        )
        self.assertContains(response, 'Invalid merge request!')

    def test_revert(self):
        unit = self.get_unit()
        # Try the merge
        response = self.client.get(
            unit.translation.get_translate_url(),
            {'checksum': unit.checksum, 'revert': 'invalid'},
            follow=True,
        )
        self.assertContains(response, 'Invalid revert request!')
        # Try the merge
        response = self.client.get(
            unit.translation.get_translate_url(),
            {'checksum': unit.checksum, 'revert': -1},
            follow=True,
        )
        self.assertContains(response, 'Invalid revert request!')


class EditResourceTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_android()


class EditResourceSourceTest(ViewTestCase):
    """Source strings (template) editing."""
    has_plurals = False

    def __init__(self, *args, **kwargs):
        self._language_code = 'en'
        super(EditResourceSourceTest, self).__init__(*args, **kwargs)

    def test_edit(self):
        translate_url = reverse(
            'translate',
            kwargs={
                'project': 'test',
                'subproject': 'test',
                'lang': 'en'
            }
        )

        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, translate_url, 1)
        unit = self.get_unit('Nazdar svete!\n')
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assert_backend(4)

    def test_edit_revert(self):
        self._language_code = 'cs'
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Edit translation
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )

        self._language_code = 'en'

        unit = translation.unit_set.get(context='hello')
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)

        # Edit source
        self.edit_unit(
            'Hello, world!\n',
            'Hello, universe!\n'
        )

        unit = translation.unit_set.get(context='hello')
        self.assertFalse(unit.translated)
        self.assertTrue(unit.fuzzy)

        # Revert source
        self.edit_unit(
            'Hello, universe!\n',
            'Hello, world!\n'
        )

        unit = translation.unit_set.get(context='hello')
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)

    def get_translation(self):
        return self.subproject.translation_set.get(
            language_code=self._language_code
        )

    def create_subproject(self):
        return self.create_android()


class EditBranchTest(EditTest):
    def create_subproject(self):
        return self.create_po_branch()


class EditMercurialTest(EditTest):
    def create_subproject(self):
        return self.create_po_mercurial()


class EditPoMonoTest(EditTest):
    monolingual = True

    def create_subproject(self):
        return self.create_po_mono()


class EditIphoneTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_iphone()


class EditJSONTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_json()


class EditJoomlaTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_joomla()


class EditRubyYAMLTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_ruby_yaml()


class EditJSONMonoTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_json_mono()


class EditJavaTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_java()


class EditXliffComplexTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_xliff('complex')


class EditXliffTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_xliff()


class EditXliffMonoTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_xliff_mono()


class EditLinkTest(EditTest):
    def create_subproject(self):
        return self.create_link()


class EditTSTest(EditTest):
    def create_subproject(self):
        return self.create_ts()


class EditTSMonoTest(EditTest):
    has_plurals = False
    monolingual = True

    def create_subproject(self):
        return self.create_ts_mono()


class ZenViewTest(ViewTestCase):
    def test_zen(self):
        response = self.client.get(
            reverse('zen', kwargs=self.kw_translation)
        )
        self.assertContains(
            response,
            'Thank you for using Weblate.'
        )
        self.assertContains(
            response,
            'Orangutan has %d bananas'
        )
        self.assertContains(
            response,
            'You have reached end of translating.'
        )

    def test_zen_invalid(self):
        response = self.client.get(
            reverse('zen', kwargs=self.kw_translation),
            {'type': 'nonexisting-type'},
            follow=True
        )
        self.assertContains(response, 'Please select a valid filter type.')

    def test_load_zen(self):
        response = self.client.get(
            reverse('load_zen', kwargs=self.kw_translation)
        )
        self.assertContains(
            response,
            'Thank you for using Weblate.'
        )
        self.assertContains(
            response,
            'Orangutan has %d bananas'
        )
        self.assertContains(
            response,
            'You have reached end of translating.'
        )

    def test_load_zen_offset(self):
        response = self.client.get(
            reverse('load_zen', kwargs=self.kw_translation),
            {'offset': '1'}
        )
        self.assertNotContains(
            response,
            'Hello, world'
        )
        self.assertContains(
            response,
            'Orangutan has %d bananas'
        )
        response = self.client.get(
            reverse('load_zen', kwargs=self.kw_translation),
            {'offset': 'bug'}
        )
        self.assertContains(
            response,
            'Hello, world'
        )

    def test_save_zen(self):
        unit = self.get_unit()
        params = {
            'checksum': unit.checksum,
            'target_0': 'Zen translation'
        }
        response = self.client.post(
            reverse('save_zen', kwargs=self.kw_translation),
            params
        )
        self.assertContains(
            response,
            'Following fixups were applied to translation: '
            'Trailing and leading whitespace'
        )

    def test_save_zen_lock(self):
        self.subproject.locked = True
        self.subproject.save()
        unit = self.get_unit()
        params = {
            'checksum': unit.checksum,
            'target_0': 'Zen translation'
        }
        response = self.client.post(
            reverse('save_zen', kwargs=self.kw_translation),
            params
        )
        self.assertContains(
            response,
            'You don&#39;t have privileges to save translations!',
        )


class EditComplexTest(ViewTestCase):
    """Test for complex manipulating translation."""

    def setUp(self):
        super(EditComplexTest, self).setUp()
        self.translation = self.get_translation()
        self.translate_url = reverse('translate', kwargs=self.kw_translation)

    def test_replace(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')

        response = self.client.post(
            reverse('replace', kwargs=self.kw_translation),
            {
                'search': 'Nazdar',
                'replacement': 'Ahoj',
            },
            follow=True
        )
        self.assertContains(
            response,
            'Search and replace completed, 1 string was updated.'
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Ahoj svete!\n')

    def test_replace_project(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')

        response = self.client.post(
            reverse('replace', kwargs=self.kw_project),
            {
                'search': 'Nazdar',
                'replacement': 'Ahoj',
            },
            follow=True
        )
        self.assertContains(
            response,
            'Search and replace completed, 1 string was updated.'
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Ahoj svete!\n')

    def test_replace_component(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')

        response = self.client.post(
            reverse('replace', kwargs=self.kw_subproject),
            {
                'search': 'Nazdar',
                'replacement': 'Ahoj',
            },
            follow=True
        )
        self.assertContains(
            response,
            'Search and replace completed, 1 string was updated.'
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Ahoj svete!\n')

    def test_merge(self):
        # Translate unit to have something to start with
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        unit = self.get_unit()
        # Try the merge
        response = self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'merge': unit.id}
        )
        self.assert_backend(1)
        # We should stay on same message
        self.assert_redirects_offset(
            response, self.translate_url, unit.position
        )

        # Test error handling
        unit2 = self.translation.unit_set.get(
            source='Thank you for using Weblate.'
        )
        response = self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'merge': unit2.id}
        )
        self.assertContains(response, 'Invalid merge request!')

    def test_revert(self):
        source = 'Hello, world!\n'
        target = 'Nazdar svete!\n'
        target_2 = 'Hei maailma!\n'
        self.edit_unit(
            source,
            target
        )
        # Ensure other edit gets different timestamp
        time.sleep(1)
        self.edit_unit(
            source,
            target_2
        )
        unit = self.get_unit()
        changes = Change.objects.content().filter(unit=unit)
        self.assertEqual(changes[1].target, target)
        self.assertEqual(changes[0].target, target_2)
        self.assert_backend(1)
        # revert it
        self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'revert': changes[1].id}
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, target)
        # check that we cannot revert to string from another translation
        self.edit_unit(
            'Thank you for using Weblate.',
            'Kiitoksia Weblaten kaytosta.'
        )
        unit2 = self.get_unit(
            source='Thank you for using Weblate.'
        )
        change = Change.objects.filter(unit=unit2)[0]
        response = self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'revert': change.id}
        )
        self.assertContains(response, 'Invalid revert request!')
        self.assert_backend(2)

    def test_edit_message(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!',
            commit_message='Fixing issue #666',
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)

        # Did the commit message got stored?
        translation = self.get_translation()
        self.assertEqual(
            'Fixing issue #666',
            translation.commit_message
        )

        # Try commiting
        translation.commit_pending(self.get_request('/'))

    def test_edit_fixup(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 0)
        self.assertEqual(len(unit.active_checks()), 0)
        self.assertEqual(unit.translation.failing_checks, 0)
        self.assert_backend(1)

    def test_edit_check(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Hello, world!\n',
        )
        # We should stay on current message
        self.assert_redirects_offset(response, self.translate_url, 0)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Hello, world!\n')
        self.assertTrue(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 1)
        self.assertEqual(len(unit.active_checks()), 1)
        self.assertEqual(unit.translation.failing_checks, 1)

        # Ignore check
        check_id = unit.checks()[0].id
        response = self.client.get(
            reverse('js-ignore-check', kwargs={'check_id': check_id})
        )
        self.assertContains(response, 'ok')
        # Should have one less check
        unit = self.get_unit()
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 1)
        self.assertEqual(len(unit.active_checks()), 0)
        self.assertEqual(unit.translation.failing_checks, 0)

        # Save with no failing checks
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should stay on current message
        self.assert_redirects_offset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 0)
        self.assertEqual(unit.translation.failing_checks, 0)
        self.assert_backend(1)

    def test_commit_push(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assert_redirects_offset(response, self.translate_url, 1)
        self.assertTrue(self.translation.repo_needs_commit())
        self.assertTrue(self.subproject.repo_needs_commit())
        self.assertTrue(self.subproject.project.repo_needs_commit())

        self.translation.commit_pending(self.get_request('/'))

        self.assertFalse(self.translation.repo_needs_commit())
        self.assertFalse(self.subproject.repo_needs_commit())
        self.assertFalse(self.subproject.project.repo_needs_commit())

        self.assertTrue(self.translation.repo_needs_push())
        self.assertTrue(self.subproject.repo_needs_push())
        self.assertTrue(self.subproject.project.repo_needs_push())

        self.translation.do_push(self.get_request('/'))

        self.assertFalse(self.translation.repo_needs_push())
        self.assertFalse(self.subproject.repo_needs_push())
        self.assertFalse(self.subproject.project.repo_needs_push())

    def test_edit_locked(self):
        self.subproject.locked = True
        self.subproject.save()
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertContains(
            response,
            'This translation is currently locked for updates!'
        )
        self.assert_backend(0)
