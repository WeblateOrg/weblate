# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext, gettext_lazy

from weblate.lang.models import Language
from weblate.trans.validators import validate_autoaccept

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models.base import ModelBase


class WorkflowSetting(models.Model):
    project = models.ForeignKey(
        "trans.Project", on_delete=models.deletion.CASCADE, null=True
    )
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    source_language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_workflow_settings",
        verbose_name=gettext_lazy("Source language"),
        help_text=gettext_lazy(
            "Translate from this language. Leave empty to use the component source language."
        ),
    )

    # This should match definitions in Project
    translation_review = models.BooleanField(
        verbose_name=gettext_lazy("Enable reviews"),
        default=settings.DEFAULT_TRANSLATION_REVIEW,
        help_text=gettext_lazy("Requires dedicated reviewers to approve translations."),
    )
    # This should match definition in Component
    enable_suggestions = models.BooleanField(
        verbose_name=gettext_lazy("Turn on suggestions"),
        default=True,
        help_text=gettext_lazy("Whether to allow translation suggestions at all."),
    )
    restrict_direct_editing = models.BooleanField(
        verbose_name=gettext_lazy("Restrict direct editing"),
        default=False,
        help_text=gettext_lazy(
            "Only users with the “Edit string when suggestions are enforced” "
            "permission can make direct changes."
        ),
    )
    # This should match definition in Component
    suggestion_voting = models.BooleanField(
        verbose_name=gettext_lazy("Suggestion voting"),
        default=False,
        help_text=gettext_lazy("Allows users to vote on suggestions."),
    )
    # This should match definition in Component
    suggestion_autoaccept = models.PositiveSmallIntegerField(
        verbose_name=gettext_lazy("Automatically accept suggestions"),
        default=0,
        help_text=gettext_lazy(
            "Automatically accept suggestions with this number of votes,"
            " use 0 to turn it off."
        ),
        validators=[validate_autoaccept],
    )

    class Meta:
        required_db_vendor = "postgresql"

    def __str__(self) -> str:
        return f"<WorkflowSetting {self.project}:{self.language}>"

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        # Serialize validation and persistence so concurrent edits cannot create cycles.
        if update_fields is not None:
            update_fields = frozenset(update_fields)
        with transaction.atomic():
            project = self.project
            if project is not None:
                type(project).objects.select_for_update().get(pk=project.pk)
            previous = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("project_id", "language_id", "source_language_id")
                .first()
            )
            current = (self.project_id, self.language_id, self.source_language_id)
            source_changed = previous != current and bool(
                self.source_language_id or (previous and previous[2])
            )
            if update_fields is not None:
                source_changed &= bool(
                    update_fields
                    & {
                        "project",
                        "project_id",
                        "language",
                        "language_id",
                        "source_language",
                        "source_language_id",
                    }
                )
            if source_changed:
                self.clean_source_language()
            super().save(
                force_insert=force_insert,
                force_update=force_update,
                using=using,
                update_fields=update_fields,
            )
            if source_changed:
                from weblate.trans.models.project import Project  # ruff: ignore[import-outside-top-level]

                Project.invalidate_translation_parent_cache()
                from weblate.trans.models.source import reconcile_project_parents  # ruff: ignore[import-outside-top-level]

                reconcile_project_parents(self.project_id)
                if previous and previous[0] != self.project_id:
                    reconcile_project_parents(previous[0])

    def clean(self) -> None:
        self.clean_source_language()
        if self.suggestion_autoaccept and not self.suggestion_voting:
            msg = gettext(
                "Accepting suggestions automatically only works with voting turned on."
            )
            raise ValidationError(
                {"suggestion_autoaccept": msg, "suggestion_voting": msg}
            )

    def clean_source_language(self) -> None:
        if self.source_language_id is None:
            return
        project = self.project
        if project is None:
            raise ValidationError(
                {
                    "source_language": gettext(
                        "Select a source language in a project workflow."
                    )
                }
            )
        if not (
            project.child_components.filter(
                translation__language_id=self.source_language_id
            ).exists()
            or type(self)
            .objects.filter(
                pk=self.pk,
                project_id=project.pk,
                language_id=self.language_id,
                source_language_id=self.source_language_id,
            )
            .exists()
        ):
            raise ValidationError(
                {
                    "source_language": gettext(
                        "The source language must exist in this project."
                    )
                }
            )
        parents = dict(
            type(self)
            .objects.filter(project_id=project.pk)
            .values_list("language_id", "source_language_id")
        )
        parents[self.language_id] = self.source_language_id
        visited = {self.language_id}
        parent: int | None = self.source_language_id
        while parent is not None:
            if parent in visited:
                raise ValidationError(
                    {
                        "source_language": gettext(
                            "Source languages cannot form a cycle."
                        )
                    }
                )
            visited.add(parent)
            parent = parents.get(parent)
