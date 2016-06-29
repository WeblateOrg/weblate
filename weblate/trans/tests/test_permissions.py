# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils.encoding import force_text

from weblate.lang.models import Language
from weblate.trans.models import (
    GroupACL, Project, Translation
)
from weblate.trans.permissions import (
    check_owner, check_permission, can_delete_comment, can_edit,
    can_author_translation,
)
from weblate.trans.tests.test_models import ModelTestCase


class PermissionsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'user', 'test@example.com', 'x'
        )
        self.owner = User.objects.create_user(
            'owner', 'owner@example.com', 'x'
        )

        self.owner.groups.add(Group.objects.get(name='Owners'))
        self.project = Project.objects.create(slug='test')
        self.project.owners.add(self.owner)

    def test_owner_owned(self):
        self.assertTrue(
            check_owner(self.owner, self.project, 'trans.author_translation')
        )

    def test_owner_no_perm(self):
        self.assertFalse(
            check_owner(self.owner, self.project, 'trans.delete_translation')
        )

    def test_owner_user(self):
        self.assertFalse(
            check_owner(self.user, self.project, 'trans.author_translation')
        )

    def test_check_owner(self):
        self.assertTrue(
            check_permission(
                self.owner, self.project, 'trans.author_translation'
            )
        )

    def test_check_user(self):
        self.assertFalse(
            check_permission(
                self.user, self.project, 'trans.author_translation'
            )
        )

    def test_delete_comment_owner(self):
        self.assertTrue(can_delete_comment(self.owner, self.project))

    def test_delete_comment_user(self):
        self.assertFalse(can_delete_comment(self.user, self.project))

    def test_cache(self):
        key = ('can_delete_comment', self.project.get_full_slug())
        self.assertTrue(not hasattr(self.user, 'alc_permissions_cache'))
        self.assertFalse(can_delete_comment(self.user, self.project))
        self.assertFalse(self.user.acl_permissions_cache[key])
        self.user.acl_permissions_cache[key] = True
        self.assertTrue(can_delete_comment(self.user, self.project))


class GroupACLTest(ModelTestCase):

    PERMISSION = "trans.save_translation"

    def setUp(self):
        super(GroupACLTest, self).setUp()

        self.user = User.objects.create_user(
            "user", 'test@example.com', 'x'
        )
        self.privileged = User.objects.create_user(
            "privileged", 'other@example.com', 'x'
        )
        self.group = Group.objects.create(name="testgroup")
        self.project = self.subproject.project
        self.subproject.translation_set.all().delete()
        self.language = Language.objects.get_default()
        self.trans = Translation.objects.create(
            subproject=self.subproject, language=self.language,
            filename="this/is/not/a.template"
        )

        app, perm = self.PERMISSION.split('.')
        self.permission = Permission.objects.get(
            codename=perm, content_type__app_label=app
        )

        self.group.permissions.add(self.permission)
        self.privileged.groups.add(self.group)

    def test_acl_lockout(self):
        '''
        Basic sanity check.
        Group ACL set on a subproject should only allow members of
        the marked group to edit it.
        '''
        self.assertTrue(can_edit(self.user, self.trans, self.PERMISSION))
        self.assertTrue(can_edit(self.privileged, self.trans, self.PERMISSION))

        acl = GroupACL.objects.create(subproject=self.subproject)
        acl.groups.add(self.group)

        self.assertTrue(can_edit(self.privileged, self.trans, self.PERMISSION))
        self.assertFalse(can_edit(self.user, self.trans, self.PERMISSION))

    def test_acl_overlap(self):
        '''
        Overlap test.
        When two ACLs can apply to a translation object, only the most
        specific one should apply.
        '''
        acl_lang = GroupACL.objects.create(language=self.language)
        acl_lang.groups.add(self.group)

        self.assertTrue(
            can_edit(self.privileged, self.trans, self.PERMISSION))

        acl_sub = GroupACL.objects.create(subproject=self.subproject)
        self.assertFalse(
            can_edit(self.privileged, self.trans, self.PERMISSION))

        acl_sub.groups.add(self.group)
        self.assertTrue(
            can_edit(self.privileged, self.trans, self.PERMISSION))

    def test_acl_str(self):
        acl = GroupACL()
        self.assertIn(
            'unspecified', force_text(acl)
        )
        acl.language = self.language
        self.assertIn(
            'language=English', force_text(acl)
        )
        acl.subproject = self.subproject
        self.assertIn(
            'subproject=Test/Test', force_text(acl)
        )
        acl.subproject = None
        acl.project = self.project
        self.assertIn(
            'project=Test', force_text(acl)
        )

    def test_acl_clean(self):
        acl = GroupACL()
        self.assertRaises(
            ValidationError,
            acl.clean
        )
        acl.project = self.project
        acl.subproject = self.subproject
        acl.clean()
        self.assertIsNone(acl.project)

    def test_acl_project(self):
        '''
        Basic sanity check for project-level actions.
        When a Group ACL is set for a project, and only for a project,
        it should apply to project-level actions on that project.
        '''
        acl = GroupACL.objects.create(project=self.project)
        acl.groups.add(self.group)
        permission = Permission.objects.get(
            codename='author_translation', content_type__app_label='trans'
        )
        self.group.permissions.add(permission)
        self.assertFalse(
            can_author_translation(self.user, self.project)
        )
        self.assertTrue(
            can_author_translation(self.privileged, self.project)
        )

    def test_affects_unrelated(self):
        '''
        Unrelated objects test.
        If I set an ACL on an object, it should not affect objects
        that it doesn't match. (in this case, a different language)
        '''
        lang_cs = Language.objects.get(code='cs')
        lang_de = Language.objects.get(code='de')
        trans_cs = Translation.objects.create(
            subproject=self.subproject, language=lang_cs,
            filename="this/is/not/a.template"
        )
        trans_de = Translation.objects.create(
            subproject=self.subproject, language=lang_de,
            filename="this/is/not/a.template"
        )

        acl = GroupACL.objects.create(language=lang_cs)
        acl.groups.add(self.group)

        self.assertTrue(can_edit(self.privileged, trans_cs, self.PERMISSION))
        self.assertFalse(can_edit(self.user, trans_cs, self.PERMISSION))

        self.assertTrue(can_edit(self.privileged, trans_de, self.PERMISSION))
        self.assertTrue(can_edit(self.user, trans_de, self.PERMISSION))

    def test_affects_partial_match(self):
        '''
        Partial match test.
        If I set an ACL on two criteria, e.g., subproject and language,
        it should not affect objects that only match one of the criteria.
        '''
        lang_cs = Language.objects.get(code='cs')
        lang_de = Language.objects.get(code='de')
        trans_cs = Translation.objects.create(
            subproject=self.subproject, language=lang_cs,
            filename="this/is/not/a.template"
        )
        trans_de = Translation.objects.create(
            subproject=self.subproject, language=lang_de,
            filename="this/is/not/a.template"
        )

        acl = GroupACL.objects.create(
            language=lang_cs,
            subproject=self.subproject
        )
        acl.groups.add(self.group)

        self.assertTrue(can_edit(self.privileged, trans_cs, self.PERMISSION))
        self.assertFalse(can_edit(self.user, trans_cs, self.PERMISSION))

        self.assertTrue(can_edit(self.privileged, trans_de, self.PERMISSION))
        self.assertTrue(can_edit(self.user, trans_de, self.PERMISSION))

    def clear_permission_cache(self):
        '''
        Clear permission cache.

        This is necessary when testing interaction of the built-in permissions
        mechanism and Group ACL. The built-in mechanism will cache results
        of `has_perm` and friends, but these can be affected by the Group ACL
        lockout. Usually the cache will get cleared on every page request,
        but here we need to do it manually.
        '''
        attribs = (
            '_perm_cache',
            '_user_perm_cache',
            '_group_perm_cache',
            'acl_permissions_cache',
        )
        for cache in attribs:
            for user in (self.user, self.privileged):
                if hasattr(user, cache):
                    delattr(user, cache)

    def test_group_locked(self):
        '''
        Limited privilege test.
        Once a group is used in a GroupACL, it is said to be "locked".
        Privileges from the locked group should not apply outside GroupACL.
        I.e., if I gain "author_translation" privilege through membership
        in a "privileged_group", applicable to Czech language, this should
        not apply to any other language.
        '''
        lang_cs = Language.objects.get(code='cs')
        lang_de = Language.objects.get(code='de')
        trans_cs = Translation.objects.create(
            subproject=self.subproject, language=lang_cs,
            filename="this/is/not/a.template"
        )
        trans_de = Translation.objects.create(
            subproject=self.subproject, language=lang_de,
            filename="this/is/not/a.template"
        )
        perm_name = 'trans.author_translation'

        self.assertFalse(can_edit(self.user, trans_cs, perm_name))
        self.assertFalse(can_edit(self.privileged, trans_cs, perm_name))
        self.assertFalse(can_edit(self.privileged, trans_de, perm_name))

        self.clear_permission_cache()
        permission = Permission.objects.get(
            codename='author_translation', content_type__app_label='trans'
        )
        self.group.permissions.add(permission)

        self.assertFalse(can_edit(self.user, trans_cs, perm_name))
        self.assertTrue(can_edit(self.privileged, trans_cs, perm_name))
        self.assertTrue(can_edit(self.privileged, trans_de, perm_name))

        self.clear_permission_cache()
        acl = GroupACL.objects.create(language=lang_cs)
        acl.groups.add(self.group)

        self.assertTrue(can_edit(self.privileged, trans_cs, perm_name))
        self.assertFalse(can_edit(self.privileged, trans_de, perm_name))

    def test_project_specific(self):
        '''
        Project specificity test.
        Project-level actions should only be affected by Group ACLs that
        are specific to the project, and don't have other criteria.
        E.g., if a GroupACL lists project+language, this should not give
        you project-level permissions.
        '''
        permission = Permission.objects.get(
            codename='author_translation', content_type__app_label='trans'
        )
        self.group.permissions.add(permission)

        acl_project_lang = GroupACL.objects.create(
            language=self.language,
            project=self.project
        )
        acl_project_lang.groups.add(self.group)

        self.assertFalse(check_permission(
            self.privileged, self.project, 'trans.author_translation'
        ))

        acl_project_only = GroupACL.objects.create(project=self.project)
        acl_project_only.groups.add(self.group)

        self.assertTrue(check_permission(
            self.privileged, self.project, 'trans.author_translation'
        ))
