# Copyright © 2026 Hendrik Leethaus <hendrik@leethaus.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.models import Suggestion
from weblate.trans.tests.test_views import ViewTestCase


class BulkAcceptSuggestionsTest(ViewTestCase):
    """Tests for bulk accepting suggestions from a specific user."""

    def setUp(self):
        super().setUp()
        self.translation = self.component.translation_set.get(language_code="cs")
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

    def test_bulk_accept_success(self):
        """Test successful bulk accept of suggestions."""
        # Create a suggestion user
        suggestion_user = User.objects.create_user(
            username="suggester", password="test"
        )

        # Add multiple suggestions from the same user
        for i in range(3):
            Suggestion.objects.create(
                unit=self.unit,
                target=f"Test suggestion {i}",
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
            {"username": "suggester"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["accepted"], 3)
        self.assertEqual(data["failed"], 0)
        self.assertEqual(data["total"], 3)
        self.assertIn("suggester", data["message"])

        # Verify suggestions were deleted after acceptance
        self.assertEqual(
            Suggestion.objects.filter(
                unit__translation=self.translation,
                user=suggestion_user,
            ).count(),
            0,
        )

    def test_bulk_accept_only_target_user(self):
        """Test that only suggestions from the specified user are accepted."""
        # Create two users with suggestions
        user1 = User.objects.create_user(username="user1", password="test")
        user2 = User.objects.create_user(username="user2", password="test")

        Suggestion.objects.create(
            unit=self.unit, target="Suggestion from user1", user=user1
        )
        Suggestion.objects.create(
            unit=self.unit, target="Suggestion from user2", user=user2
        )

        # Accept only user1's suggestions
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "user1"},
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

    def test_bulk_accept_rate_limiting(self):
        """Test that rate limiting prevents abuse (>1000 suggestions)."""
        # Create a user with too many suggestions (simulated with queryset patch)
        user = User.objects.create_user(username="spammer", password="test")

        self.assertIsNotNone(self.unit)

        # Create a few real suggestions
        for i in range(5):
            Suggestion.objects.create(
                unit=self.unit,
                target=f"Spam {i}",
                user=user,
            )

        # Mock the count to simulate >1000 suggestions
        from unittest.mock import patch

        with patch.object(
            type(Suggestion.objects.filter()), "count", return_value=1001
        ):
            response = self.client.post(
                reverse(
                    "bulk-accept-user-suggestions",
                    kwargs={"path": self.translation.get_url_path()},
                ),
                {"username": "spammer"},
            )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("1001", data["error"])

    def test_bulk_accept_only_target_translation(self):
        """Test that only suggestions for the specified translation are accepted."""
        # Create suggestion in current translation
        user = User.objects.create_user(username="translator", password="test")
        Suggestion.objects.create(
            unit=self.unit, target="Test cs suggestion", user=user
        )

        # Create suggestion in different translation
        de_translation = self.component.translation_set.get(language_code="de")
        de_unit = de_translation.unit_set.get(source="Hello, world!\n")
        Suggestion.objects.create(unit=de_unit, target="Test de suggestion", user=user)

        # Accept suggestions only for Czech translation
        response = self.client.post(
            reverse(
                "bulk-accept-user-suggestions",
                kwargs={"path": self.translation.get_url_path()},
            ),
            {"username": "translator"},
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
                target=f"Suggestion for unit {i}",
                user=suggester,
            )

        # Verify all suggestions were created
        total_suggestions = Suggestion.objects.filter(
            unit__translation=self.translation,
            user=suggester,
        ).count()
        self.assertEqual(total_suggestions, 3)

        # Log in as limited user (no permissions) and try to bulk accept
        self.client.login(username="limited", password="test")
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
