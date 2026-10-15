# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

import json
import os

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from weblate.accounts.models import Profile
from weblate.accounts.notifications import (
    NOTIFICATIONS,
    NotificationFrequency,
    NotificationScope,
)
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Category, Component, Project, SavedSearch
from weblate.trans.tests.utils import TempDirMixin, get_test_file

USERDATA_JSON = get_test_file("userdata.json")


class CommandTest(TestCase, TempDirMixin):
    """Test for management commands."""

    def test_userdata(self) -> None:
        # Create test user
        language = Language.objects.get(code="cs")
        user = User.objects.create_user("testuser", "test@example.com", "x")
        user.profile.translated = 1000
        user.profile.languages.add(language)
        user.profile.secondary_languages.add(language)
        user.profile.save()
        user.profile.watched.add(Project.objects.create(name="name", slug="name"))

        self.create_temp()
        self.addCleanup(self.remove_temp)
        output = os.path.join(self.tempdir, "users.json")
        call_command("dumpuserdata", output)

        user.profile.languages.clear()
        user.profile.secondary_languages.clear()

        call_command("importuserdata", output)

        profile = Profile.objects.get(user__username="testuser")
        self.assertEqual(profile.translated, 2000)
        self.assertTrue(profile.languages.filter(code="cs").exists())
        self.assertTrue(profile.secondary_languages.filter(code="cs").exists())
        self.assertTrue(profile.watched.exists())

    def test_dumpuserdata_batches_subscription_categories(self) -> None:
        project = Project.objects.create(name="Export", slug="export")
        parent = Category(name="Parent", slug="parent", project=project)
        Category.objects.bulk_create([parent])
        child = Category(name="Child", slug="child", project=project, category=parent)
        Category.objects.bulk_create([child])
        component = Component.objects.bulk_create(
            [
                Component(
                    name="Messages",
                    slug="messages",
                    project=project,
                    category=child,
                    repo="local:",
                    filemask="locale/*.po",
                    file_format="po",
                )
            ]
        )[0]
        users = [
            User.objects.create_user(
                f"export-{index}", f"export-{index}@example.com", "x"
            )
            for index in range(3)
        ]
        excluded = [
            User.objects.create_user(
                "inactive", "inactive@example.com", "x", is_active=False
            ),
            User.objects.create_user("bot", "bot@example.com", "x", is_bot=True),
        ]
        for user in [*users, *excluded]:
            SavedSearch.objects.create(user=user, name="Search", query="has:comment")
            user.subscription_set.create(
                notification=NOTIFICATIONS[0].get_name(),
                scope=NotificationScope.SCOPE_COMPONENT,
                frequency=NotificationFrequency.FREQ_DAILY,
                component=component,
            )

        self.create_temp()
        self.addCleanup(self.remove_temp)
        output = os.path.join(self.tempdir, "users.json")
        with CaptureQueriesContext(connection) as queries:
            call_command("dumpuserdata", output)

        with open(output, encoding="utf-8") as handle:
            exported = {item["basic"]["username"]: item for item in json.load(handle)}
        for user in users:
            self.assertIn(user.username, exported)
            self.assertEqual(
                exported[user.username]["saved_searches"],
                [{"name": "Search", "query": "has:comment", "description": ""}],
            )
            self.assertIn(
                "export/parent/child/messages",
                [
                    rule["component"]
                    for rule in exported[user.username]["notifications"]
                ],
            )
        for user in excluded:
            self.assertNotIn(user.username, exported)
        self.assertEqual(
            sum('FROM "accounts_subscription"' in query["sql"] for query in queries),
            1,
        )
        self.assertEqual(
            sum('FROM "trans_savedsearch"' in query["sql"] for query in queries),
            1,
        )
        self.assertEqual(
            sum('FROM "trans_category"' in query["sql"] for query in queries),
            2,
        )

    def test_userdata_compat(self) -> None:
        """Test importing user data from pre 3.6 release."""
        User.objects.create_user("test-3.6", "test36@example.com", "x")
        Project.objects.create(name="test", slug="test")
        call_command("importuserdata", USERDATA_JSON)
        profile = Profile.objects.get(user__username="test-3.6")
        self.assertTrue(profile.languages.filter(code="cs").exists())
        self.assertTrue(profile.secondary_languages.filter(code="cs").exists())
        self.assertTrue(profile.watched.exists())
