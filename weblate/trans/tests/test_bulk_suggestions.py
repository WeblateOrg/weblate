# Copyright © 2026 Hendrik Leethaus <hendrik@leethaus.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.models import Suggestion
from weblate.trans.tasks import (
    bulk_accept_user_suggestions as bulk_accept_user_suggestions_task,
)
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_APPROVED


class BulkAcceptSuggestionsTest(ViewTestCase):
    """Tests for bulk accepting suggestions from a specific user."""

    def setUp(self):
        super().setUp()
        self.translation = self.component.translation_set.get(language_code="cs")
        # Source unit is "Hello, world!\n"
        self.unit = self.translation.unit_set.get(
            source="Hello, world!\n",
        )
        # Give test user permission to accept suggestions
        self.project.add_user(self.user, "Administration")

    def test_bulk_accept_requires_post(self):
        """Test that GET request is not allowed."""
        response = self.client.get(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            )
        )
        self.assertEqual(response.status_code, 405)

    def test_bulk_accept_requires_login(self):
        """Test that anonymous users cannot bulk accept."""
        self.client.logout()
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "testuser"},
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_bulk_accept_requires_permission(self):
        """Test that users without suggestion.accept permission get 403."""
        # Create a user without permissions
        User.objects.create_user(username="noperm", password="test")
        self.client.login(username="noperm", password="test")

        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "testuser"},
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("permission", data["error"].lower())

    def test_bulk_accept_invalid_username(self):
        """Test that invalid username returns 400."""
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "nonexistent_user_12345"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("not found", data["error"].lower())

    def test_bulk_accept_preview_count(self):
        """Test that preview returns matching suggestion count."""
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        user = User.objects.create_user(username="previewer", password="test")
        other_user = User.objects.create_user(username="other-preview", password="test")
        Suggestion.objects.create(
            unit=self.unit, target="Preview suggestion 1!\n", user=user
        )
        Suggestion.objects.create(
            unit=self.unit, target="Preview suggestion 2!\n", user=user
        )
        Suggestion.objects.create(
            unit=self.unit, target="Other preview suggestion!\n", user=other_user
        )

        de_translation = self.component.translation_set.get(language_code="de")
        de_unit = de_translation.unit_set.get(source="Hello, world!\n")
        Suggestion.objects.create(
            unit=de_unit, target="Preview suggestion de!\n", user=user
        )

        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "previewer", "preview": "1"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["preview"])
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["username"], "previewer")
        self.assertTrue(data["can_approve"])
        self.assertEqual(Suggestion.objects.filter(user=user).count(), 3)

    def test_bulk_accept_requires_confirmation(self):
        """Test that accepting requires the confirmed marker."""
        suggestion_user = User.objects.create_user(
            username="unconfirmed-suggester", password="test"
        )
        Suggestion.objects.create(
            unit=self.unit,
            target="Unconfirmed suggestion!\n",
            user=suggestion_user,
        )

        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "unconfirmed-suggester"},
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("confirmation", data["error"].lower())
        self.assertTrue(Suggestion.objects.filter(user=suggestion_user).exists())

    def test_bulk_accept_success(self):
        """Test successful bulk accept of suggestions."""
        # Create a suggestion user
        suggestion_user = User.objects.create_user(
            username="suggester", password="test"
        )

        # Add multiple suggestions from the same user
        for i in range(3):
            # Added !\n to match source unit formatting and pass checks
            Suggestion.objects.create(
                unit=self.unit,
                target=f"Test suggestion {i}!\n",
                user=suggestion_user,
            )

        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=suggestion_user,
            ).count(),
            3,
        )

        # Bulk accept all suggestions
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "suggester", "confirmed": "1"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["accepted"], 3)
        self.assertEqual(data["failed"], 0)
        self.assertEqual(data["total"], 3)
        self.assertIn("suggester", data["message"])

        # Check Django messages
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level_tag, "success")

        # Verify suggestions were deleted after acceptance
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=suggestion_user,
            ).count(),
            0,
        )

    def test_bulk_accept_skips_failing_checks(self):
        """Test that suggestions with failing checks are skipped."""
        suggestion_user = User.objects.create_user(
            username="check_suggester", password="test"
        )

        # 1. Valid suggestion (matches source format !\n)
        s1 = Suggestion.objects.create(
            unit=self.unit, target="Valid suggestion!\n", user=suggestion_user
        )

        # 2. Invalid suggestion (missing ! and \n) -> Fails checks
        s2 = Suggestion.objects.create(
            unit=self.unit, target="Invalid suggestion", user=suggestion_user
        )

        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "check_suggester", "confirmed": "1"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["accepted"], 1)
        self.assertEqual(data["failed"], 1)

        # Verify messages (Warning level because of partial failure)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level_tag, "warning")

        # Verify valid suggestion was accepted (deleted)
        self.assertFalse(Suggestion.objects.filter(pk=s1.pk).exists())
        # Verify invalid suggestion remains in DB
        self.assertTrue(Suggestion.objects.filter(pk=s2.pk).exists())

    def test_bulk_accept_only_target_user(self):
        """Test that only suggestions from the specified user are accepted."""
        # Create two users with suggestions
        user1 = User.objects.create_user(username="user1", password="test")
        user2 = User.objects.create_user(username="user2", password="test")

        Suggestion.objects.create(
            unit=self.unit, target="Suggestion from user1!\n", user=user1
        )
        Suggestion.objects.create(
            unit=self.unit, target="Suggestion from user2!\n", user=user2
        )

        # Accept only user1's suggestions
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "user1", "confirmed": "1"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["accepted"], 1)

        # Verify only user1's suggestions were accepted
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=user1,
            ).count(),
            0,
        )
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=user2,
            ).count(),
            1,
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_bulk_accept_no_size_limit_schedules_task(self):
        """Test that large batches are scheduled instead of blocked."""
        user = User.objects.create_user(username="spammer", password="test")

        self.assertIsNotNone(self.unit)

        for i in range(5):
            Suggestion.objects.create(
                unit=self.unit,
                target=f"Spam {i}!\n",
                user=user,
            )
        return_url = f"{self.unit.get_absolute_url()}#suggestions"

        with (
            patch.object(type(Suggestion.objects.filter()), "count", return_value=1001),
            patch(
                "weblate.trans.views.bulk_suggestions."
                "bulk_accept_user_suggestions_task.delay",
                return_value=SimpleNamespace(id="task-bulk-accept"),
            ) as mocked_delay,
        ):
            response = self.client.post(
                reverse(
                    "bulk-accept-user-suggestions",
                    kwargs={"path": self.translation.get_url_path()},
                ),
                {
                    "username": "spammer",
                    "confirmed": "1",
                    "return_url": return_url,
                },
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["completed"])
        self.assertEqual(data["task_id"], "task-bulk-accept")
        self.assertEqual(data["total"], 1001)
        self.assertIn("1001", data["message"])

        mocked_delay.assert_called_once_with(
            translation_id=self.translation.id,
            target_user_id=user.id,
            user_id=self.user.id,
            approve=False,
            return_url=return_url,
        )
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=user,
            ).count(),
            5,
        )

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level_tag, "success")
        self.assertEqual(messages[0].extra_tags, "task:task-bulk-accept")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_bulk_accept_and_approve_schedules_task(self):
        """Test that accepting and approving schedules approval mode."""
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        user = User.objects.create_user(username="review-spammer", password="test")
        Suggestion.objects.create(
            unit=self.unit,
            target="Review spam!\n",
            user=user,
        )

        with patch(
            "weblate.trans.views.bulk_suggestions."
            "bulk_accept_user_suggestions_task.delay",
            return_value=SimpleNamespace(id="task-bulk-approve"),
        ) as mocked_delay:
            response = self.client.post(
                reverse(
                    "bulk-accept-user-suggestions",
                    kwargs={"path": self.translation.get_url_path()},
                ),
                {"username": "review-spammer", "confirmed": "1", "approve": "1"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("approving", data["message"])
        mocked_delay.assert_called_once_with(
            translation_id=self.translation.id,
            target_user_id=user.id,
            user_id=self.user.id,
            approve=True,
            return_url=self.translation.get_translate_url(),
        )

    def test_bulk_accept_and_approve_requires_permission(self):
        """Test that approval mode requires review permission."""
        user = User.objects.create_user(username="review-denied", password="test")
        Suggestion.objects.create(
            unit=self.unit,
            target="Review denied!\n",
            user=user,
        )

        def has_perm(_user, permission, _obj):
            return permission == "suggestion.accept"

        with patch("weblate.trans.views.bulk_suggestions.User.has_perm", has_perm):
            response = self.client.post(
                reverse(
                    "bulk-accept-user-suggestions",
                    kwargs={"path": self.translation.get_url_path()},
                ),
                {"username": "review-denied", "confirmed": "1", "approve": "1"},
            )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("approve", data["error"])

    def test_bulk_accept_only_target_translation(self):
        """Test that only suggestions for the specified translation are accepted."""
        # Create suggestion in current translation
        user = User.objects.create_user(username="translator", password="test")
        Suggestion.objects.create(
            unit=self.unit, target="Test cs suggestion!\n", user=user
        )

        # Create suggestion in different translation
        de_translation = self.component.translation_set.get(language_code="de")
        de_unit = de_translation.unit_set.get(source="Hello, world!\n")
        Suggestion.objects.create(
            unit=de_unit, target="Test de suggestion!\n", user=user
        )

        # Accept suggestions only for Czech translation
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "translator", "confirmed": "1"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["accepted"], 1)

        # Verify only Czech suggestion was accepted
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=user,
            ).count(),
            0,
        )
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=de_translation,
                user=user,
            ).count(),
            1,
        )

    def test_bulk_accept_partial_permission_failure(self):
        """Test that some suggestions fail if user lacks per-unit permissions."""
        # Create a user WITHOUT project permissions (no add_user call)
        limited_user = User.objects.create_user(username="limited", password="test")

        # Create a suggester user
        suggester = User.objects.create_user(username="suggester", password="test")

        # Get multiple units from the translation
        units = list(self.translation.unit_set.all()[:3])
        self.assertGreaterEqual(len(units), 3, "Need at least 3 units for this test")

        # Create suggestions from the same user for all units
        for i, unit in enumerate(units):
            Suggestion.objects.create(
                unit=unit,
                target=f"Suggestion for unit {i}!\n",
                user=suggester,
            )

        # Verify all suggestions were created
        total_suggestions = Suggestion.objects.filter(
            unit__translation=self.translation,
            user=suggester,
        ).count()
        self.assertEqual(total_suggestions, 3)

        # Log in as limited user (no permissions) and try to bulk accept
        self.client.login(username=limited_user.username, password="test")
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "suggester"},
        )

        # User without permissions should get 403
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("permission", data["error"].lower())

        # Verify no suggestions were accepted
        remaining = Suggestion.objects.filter(
            unit__translation=self.translation,
            user=suggester,
        ).count()
        self.assertEqual(remaining, 3)

    def test_bulk_accept_task_rechecks_permissions(self):
        """Test that the task skips suggestions when permissions are removed."""
        suggester = User.objects.create_user(username="task-suggester", password="test")
        Suggestion.objects.create(
            unit=self.unit, target="Task suggestion!\n", user=suggester
        )

        with patch("weblate.trans.tasks.User.has_perm", return_value=False):
            result = bulk_accept_user_suggestions_task(
                translation_id=self.translation.id,
                target_user_id=suggester.id,
                user_id=self.user.id,
            )

        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["total"], 1)
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=suggester,
            ).count(),
            1,
        )

    def test_bulk_accept_task_approves(self):
        """Test that approval mode accepts suggestions as approved."""
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        suggester = User.objects.create_user(username="task-reviewer", password="test")
        Suggestion.objects.create(
            unit=self.unit, target="Task approved!\n", user=suggester
        )

        result = bulk_accept_user_suggestions_task(
            translation_id=self.translation.id,
            target_user_id=suggester.id,
            user_id=self.user.id,
            approve=True,
        )

        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["failed"], 0)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.state, STATE_APPROVED)

    def test_bulk_accept_task_returns_url(self):
        """Test that the task returns a URL for progress completion reload."""
        suggester = User.objects.create_user(username="task-url", password="test")
        Suggestion.objects.create(unit=self.unit, target="Task URL!\n", user=suggester)

        result = bulk_accept_user_suggestions_task(
            translation_id=self.translation.id,
            target_user_id=suggester.id,
            user_id=self.user.id,
            return_url="/translate/current/#suggestions",
        )

        self.assertEqual(result["url"], "/translate/current/#suggestions")
        completion_message = result["completion_message"]
        self.assertIsInstance(completion_message, dict)
        self.assertIn(
            completion_message["level"], {"error", "info", "success", "warning"}
        )
        self.assertEqual(completion_message["text"], result["message"])

    def test_bulk_accept_task_uses_user_language(self):
        """Test that task completion messages use the requesting user's language."""
        self.user.profile.language = "cs"
        self.user.profile.save(update_fields=["language"])
        suggester = User.objects.create_user(username="task-language", password="test")
        Suggestion.objects.create(
            unit=self.unit, target="Task language!\n", user=suggester
        )

        with patch("weblate.trans.tasks.override") as mocked_override:
            bulk_accept_user_suggestions_task(
                translation_id=self.translation.id,
                target_user_id=suggester.id,
                user_id=self.user.id,
            )

        mocked_override.assert_called_once_with("cs")

    def test_bulk_accept_task_reports_progress(self):
        """Test that the task reports Celery progress."""
        suggester = User.objects.create_user(username="progress-user", password="test")
        for i in range(2):
            Suggestion.objects.create(
                unit=self.unit,
                target=f"Progress suggestion {i}!\n",
                user=suggester,
            )
        task = SimpleNamespace(
            request=SimpleNamespace(id="task-progress"), update_state=Mock()
        )

        with patch("weblate.trans.tasks.current_task", task):
            result = bulk_accept_user_suggestions_task(
                translation_id=self.translation.id,
                target_user_id=suggester.id,
                user_id=self.user.id,
            )

        self.assertEqual(result["accepted"], 2)
        progress_values = [
            call.kwargs["meta"]["progress"] for call in task.update_state.call_args_list
        ]
        self.assertEqual(progress_values, [0, 50, 100])
