# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext, gettext_lazy

from weblate.lang.models import Language
from weblate.trans.validators import validate_autoaccept


class WorkflowSetting(models.Model):
    project = models.ForeignKey(
        "trans.Project", on_delete=models.deletion.CASCADE, null=True
    )
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)

    # This should match definitions in Project
    translation_review = models.BooleanField(
        verbose_name=gettext_lazy("Enable reviews"),
        default=False,
        help_text=gettext_lazy("Requires dedicated reviewers to approve translations."),
    )
    # This should match definition in Component
    enable_suggestions = models.BooleanField(
        verbose_name=gettext_lazy("Turn on suggestions"),
        default=True,
        help_text=gettext_lazy("Whether to allow translation suggestions at all."),
    )
    # This should match definition in Component
    suggestion_voting = models.BooleanField(
        verbose_name=gettext_lazy("Suggestion voting"),
        default=False,
        help_text=gettext_lazy(
            "Users can only vote for suggestions and can’t make direct translations."
        ),
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

    def __str__(self) -> str:
        return f"<WorkflowSetting {self.project}:{self.language}>"

    def clean(self) -> None:
        if self.suggestion_autoaccept and not self.suggestion_voting:
            msg = gettext(
                "Accepting suggestions automatically only works with voting turned on."
            )
            raise ValidationError(
                {"suggestion_autoaccept": msg, "suggestion_voting": msg}
            )
