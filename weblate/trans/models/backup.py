# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Private consent and provenance for authors claimed by project backups."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from collections.abc import Generator

    from weblate.auth.models import Invitation, User

_author_claim: ContextVar[BackupAuthorClaim | None] = ContextVar(
    "backup_author_claim", default=None
)


class BackupAuthorClaim(models.Model):
    """An internal claim, bound to a particular invitation and restored project."""

    project = models.ForeignKey("trans.Project", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    invitation = models.OneToOneField(
        "weblate_auth.Invitation",
        null=True,
        on_delete=models.SET_NULL,
        related_name="backup_author_claim",
    )
    accepted_at = models.DateTimeField(null=True)

    def __str__(self) -> str:
        return f"Backup author claim {self.pk} in project {self.project_id}"

    @transaction.atomic
    def accept(
        self,
        invitation: Invitation,
        user: User,
    ) -> None:
        current = BackupAuthorClaim.objects.select_for_update(no_key=True).get(
            pk=self.pk
        )
        if current.accepted_at is not None:
            return
        if (
            current.invitation_id != invitation.pk
            or current.user_id != user.pk
            or invitation.group.defining_project_id != current.project_id
            or invitation.is_expired()
            or not invitation.matches_user(user)
        ):
            msg = "Backup authorship claim does not match its invitation."
            raise ValueError(msg)
        current.accepted_at = timezone.now()
        current.save(update_fields=["accepted_at"])
        current.reconcile()
        transaction.on_commit(current.reconcile)

    @transaction.atomic
    def reconcile(self) -> None:
        """
        Cover content committed on either side of concurrent consent.

        Both consent and content consumers run this after committing. The later
        commit therefore observes both the accepted claim and the consumed rows.
        No consumer holds a claim lock while waiting for pending-row locks.
        """
        from weblate.accounts.models import TeamAuditLog  # ruff: ignore[import-outside-top-level]
        from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]
        from weblate.screenshots.models import Screenshot  # ruff: ignore[import-outside-top-level]
        from weblate.trans.models import (  # ruff: ignore[import-outside-top-level]
            Change,
            Comment,
            PendingUnitChange,
            Suggestion,
            Vote,
        )

        current = (
            BackupAuthorClaim.objects.filter(pk=self.pk, accepted_at__isnull=False)
            .select_for_update(no_key=True, of=("self",))
            .select_related("user", "project")
            .first()
        )
        if current is None:
            return
        user = current.user
        anonymous = get_anonymous()
        # Different claimed voters share one anonymous vote. Lock all affected
        # suggestions in order before changing authors or retiring placeholders.
        list(
            Suggestion.objects.filter(
                unit__translation__component__project_id=current.project_id,
            )
            .filter(
                Q(backup_author_claim=current)
                | Q(pk__in=current.votes.values_list("suggestion_id", flat=True))
            )
            .order_by("pk")
            .select_for_update(no_key=True, of=("self",))
            .values_list("pk", flat=True)
        )
        counts = {}
        for model, field, project_lookup in (
            (Comment, "user", "unit__translation__component__project_id"),
            (Suggestion, "user", "unit__translation__component__project_id"),
            (Screenshot, "user", "translation__component__project_id"),
            # Consuming a suggestion can propagate into another project. Its
            # pending changes and history retain the original private claim.
            (PendingUnitChange, "author", None),
            (Change, "author", None),
        ):
            scope = (
                {project_lookup: current.project_id}
                if project_lookup is not None
                else {}
            )
            counts[model.__name__] = model.objects.filter(
                backup_author_claim=current,
                **{field: anonymous, **scope},
            ).update(**{field: user})
        counts["Vote"] = 0
        for vote in current.votes.filter(
            suggestion__unit__translation__component__project_id=current.project_id
        ):
            _vote, created = Vote.objects.get_or_create(
                suggestion_id=vote.suggestion_id,
                user=user,
                defaults={"value": vote.value},
            )
            counts["Vote"] += int(created)
            if (
                vote.placeholder_id
                and not BackupAuthorVote.objects.filter(
                    placeholder_id=vote.placeholder_id
                )
                .exclude(claim=current)
                .exists()
            ):
                Vote.objects.filter(pk=vote.placeholder_id, user=anonymous).delete()
        current.votes.all().delete()
        if any(counts.values()):
            TeamAuditLog.objects.create(
                project=current.project,
                scope="project",
                scope_label=current.project.slug,
                team_name="Imported authorship",
                actor=user,
                event="changed",
                details={
                    "restored_authorship": {"username": user.username, "counts": counts}
                },
            )


class BackupAuthorVote(models.Model):
    """Keep distinct claimed votes while their anonymous display is coalesced."""

    claim = models.ForeignKey(
        BackupAuthorClaim, on_delete=models.CASCADE, related_name="votes"
    )
    suggestion = models.ForeignKey("trans.Suggestion", on_delete=models.CASCADE)
    placeholder = models.ForeignKey("trans.Vote", null=True, on_delete=models.CASCADE)
    value = models.SmallIntegerField()

    def __str__(self) -> str:
        return f"Backup vote {self.pk} for suggestion {self.suggestion_id}"


class BackupAuthorshipMixin(models.Model):
    # Internal consent provenance, deliberately absent from exports and serializers.
    backup_author_claim = models.ForeignKey(
        BackupAuthorClaim,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


@contextmanager
def backup_author_context(
    claim_id: int | None, project_id: int, *, author_id: int | None = None
) -> Generator[User | None, None, None]:
    """Preserve provenance and reconcile concurrent consent after consumption."""
    from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]
    from weblate.trans.models.pending import PendingUnitChange  # ruff: ignore[import-outside-top-level]

    if claim_id is None:
        yield None
        return
    with transaction.atomic():
        claim = BackupAuthorClaim.objects.select_related("user").get(pk=claim_id)
        if (
            author_id is not None
            and author_id != get_anonymous().pk
            and not (claim.accepted_at is not None and author_id == claim.user_id)
        ):
            yield None
            return
        # A destination commit may consume changes propagated from the restored
        # project. Only existing, privately tracked pending rows extend consent
        # to that destination; a project identifier alone cannot do so.
        if (
            claim.project_id != project_id
            and not PendingUnitChange.objects.filter(
                backup_author_claim=claim,
                unit__translation__component__project_id=project_id,
            ).exists()
        ):
            yield None
            return
        token = _author_claim.set(claim)
        try:
            yield claim.user if claim.accepted_at is not None else get_anonymous()
        finally:
            _author_claim.reset(token)
        transaction.on_commit(claim.reconcile)


def apply_backup_authorship(kwargs: dict[str, Any]) -> None:
    """Carry consent provenance without changing the initiating actor."""
    from weblate.auth.models import get_anonymous  # ruff: ignore[import-outside-top-level]

    claim = _author_claim.get()
    if claim is None:
        return
    author = kwargs.get("author")
    author_id = author.pk if author is not None else kwargs.get("author_id")
    if author_id != get_anonymous().pk and not (
        claim.accepted_at is not None and author_id == claim.user_id
    ):
        return
    kwargs["backup_author_claim_id"] = claim.pk
    kwargs.pop("author_id", None)
    kwargs["author"] = claim.user if claim.accepted_at is not None else get_anonymous()
