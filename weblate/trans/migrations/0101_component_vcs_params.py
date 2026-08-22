# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from itertools import batched

from django.db import migrations, models

import weblate.trans.validators

FORCE_PUSH_VCS = "git-force-push"
GIT_VCS = "git"
FORCE_PUSH_PARAM = "git_force_push"
BATCH_SIZE = 500


def migrate_force_push_vcs(apps, schema_editor) -> None:
    """Turn the dedicated force push backend into a Git parameter."""
    Component = apps.get_model("trans", "Component")

    def convert(component):
        component.vcs = GIT_VCS
        component.vcs_params = {**(component.vcs_params or {}), FORCE_PUSH_PARAM: True}
        return component

    queryset = Component.objects.filter(vcs=FORCE_PUSH_VCS).iterator(
        chunk_size=BATCH_SIZE
    )
    for batch in batched(queryset, BATCH_SIZE):
        Component.objects.bulk_update(
            [convert(component) for component in batch], ["vcs", "vcs_params"]
        )


def reverse_force_push_vcs(apps, schema_editor) -> None:
    Component = apps.get_model("trans", "Component")

    def convert(component):
        component.vcs = FORCE_PUSH_VCS
        component.vcs_params.pop(FORCE_PUSH_PARAM, None)
        return component

    queryset = Component.objects.filter(
        vcs=GIT_VCS, vcs_params__git_force_push=True
    ).iterator(chunk_size=BATCH_SIZE)
    for batch in batched(queryset, BATCH_SIZE):
        Component.objects.bulk_update(
            [convert(component) for component in batch], ["vcs", "vcs_params"]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0100_remove_inexact_hook_match_alerts"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="vcs_params",
            field=models.JSONField(
                blank=True,
                default=dict,
                validators=[weblate.trans.validators.validate_vcs_parameters],
                verbose_name="Version control parameters",
            ),
        ),
        migrations.RunPython(
            migrate_force_push_vcs,
            reverse_code=reverse_force_push_vcs,
            elidable=True,
        ),
    ]
