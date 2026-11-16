# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from social_core.exceptions import AuthConfigurationError, AuthSessionError
from social_core.groups import group_sync_targets
from social_django.strategy import DjangoStrategy

from weblate.accounts.flows import PASSWORD_RESET_EMAIL_SESSION
from weblate.auth.models import Group, User
from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from typing import Any

    from social_core.backends.base import BaseAuth
    from social_core.storage import PartialMixin

    from weblate.auth.models import AuthenticatedHttpRequest


class WeblateStrategy(DjangoStrategy):
    invalid_partial_token: str | None = None

    def partial_load(self, token: str) -> PartialMixin | None:
        from weblate.accounts.pipeline import (  # ruff: ignore[import-outside-top-level]
            validate_password_reset,
        )

        partial = super().partial_load(token)
        if partial is None:
            return partial
        if partial.pipeline_type == "authentication" and partial.kwargs.get(
            "weblate_auth_pipeline"
        ) != list(self.get_pipeline(self.get_backend(partial.backend))):
            # Saved positions must never resume against a reordered pipeline,
            # where the same index could skip an authentication check.
            self.invalidate_partial(token)
            raise AuthSessionError(
                self.get_backend(partial.backend),
                code="weblate.confirmation_expired",
                stage="pipeline",
            )
        if partial.backend == "email" and (user := partial.kwargs.get("user")):
            # Linking and removal also verify codes before store_email(). Use
            # the same account-first lock order as recovery and revocation.
            partial.kwargs["user"] = (
                User.objects.select_for_update().filter(pk=user.pk).first()
            )
        if (
            partial.backend == "email"
            and partial.kwargs.get("weblate_action") == "reset"
        ):
            try:
                # Acquire the account lock before mail_validation can lock a
                # code row. Provider refresh invalidates codes in that order.
                validate_password_reset(
                    self.get_backend(partial.backend),
                    partial.kwargs.get("details", {}),
                    partial.kwargs.get("weblate_reset_user"),
                    partial.kwargs.get("user"),
                )
            except AuthSessionError:
                self.invalidate_partial(token)
                raise
        # Other authentication flows do not carry an e-mail-addition auth hash.
        if "weblate_email_auth_hash" not in partial.kwargs:
            return partial
        saved_hash = partial.kwargs["weblate_email_auth_hash"]
        user = partial.kwargs.get("user")
        if (
            isinstance(saved_hash, str)
            and user is not None
            and constant_time_compare(saved_hash, user.get_session_auth_hash())
        ):
            return partial
        self.invalidate_partial(token)
        raise AuthSessionError(
            self.get_backend(partial.backend),
            code="weblate.confirmation_expired",
            stage="pipeline",
        )

    def invalidate_partial(self, token: str) -> None:
        # E-mail completion can roll back the pipeline transaction. Remember
        # this cleanup so the view can repeat it outside that transaction.
        self.invalid_partial_token = token
        self.clean_partial_pipeline(token)
        self.session_pop("reauthenticate")
        self.session_pop("reauthenticate_done")

    def sync_user_groups(
        self,
        user: User,
        groups: list[str] | None,
        *,
        backend: BaseAuth,
        response: dict[str, Any],
        **kwargs: object,
    ) -> None:
        """Apply provider-owned memberships through audited team operations."""
        if kwargs.get("weblate_action") in {"reset", "remove"}:
            return
        desired, managed = group_sync_targets(backend, groups, response)
        if not managed:
            return
        if any(
            not isinstance(target, int) or isinstance(target, bool) or target <= 0
            for target in managed
        ):
            raise AuthConfigurationError(
                backend,
                code="invalid_setting",
                parameter="GROUPS_MAP",
                stage="pipeline",
            )
        desired_ids = cast("set[int]", desired)
        managed_ids = cast("set[int]", managed)
        request = cast("AuthenticatedHttpRequest | None", self.request)
        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            teams = {team.pk: team for team in Group.objects.filter(pk__in=managed_ids)}
            if set(teams) != managed_ids:
                raise AuthConfigurationError(
                    backend,
                    "A mapped Weblate team does not exist",
                    code="invalid_setting",
                    parameter="GROUPS_MAP",
                    stage="pipeline",
                )
            current = set(user.groups.values_list("pk", flat=True))
            for team_id in (current & managed_ids) - desired_ids:
                user.remove_team(request, teams[team_id])
            for team_id in desired_ids - current:
                user.add_team(request, teams[team_id])
            if (current & managed_ids) != desired_ids:
                user.clear_permissions_cache()

    def get_setting(self, name):
        if name == "SOCIAL_AUTH_EMAIL_VALIDATION_EXPIRED_THRESHOLD":
            return settings.AUTH_TOKEN_VALID
        return super().get_setting(name)

    @cached_property
    def _site_url(self):
        return urlparse(get_site_url())

    def get_request_data(self, merge=True):
        if not self.request:
            return {}
        if merge:
            data = self.request.GET.copy()
            data.update(self.request.POST)
        elif self.request.method == "POST":
            data = self.request.POST.copy()
        else:
            data = self.request.GET.copy()
        if (
            self.session.get("password_reset")
            and self.session.get(PASSWORD_RESET_EMAIL_SESSION)
            and "partial_token" not in data
        ):
            data["email"] = self.session[PASSWORD_RESET_EMAIL_SESSION]
        # Weblate defaults invalid return URLs to the account page.
        if "next" in data and not url_has_allowed_host_and_scheme(
            data["next"], allowed_hosts=None
        ):
            data["next"] = f"{reverse('profile')}#account"
        return data

    def build_absolute_uri(self, path=None):
        if self.request:
            # ruff: ignore[private-member-access]
            self.request._current_scheme_host = get_site_url()
        return super().build_absolute_uri(path)

    def request_is_secure(self):
        return settings.ENABLE_HTTPS

    def request_port(self):
        return self._site_url.port

    def request_host(self):
        return self._site_url.hostname
