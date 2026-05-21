# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models

import weblate.auth.models


class Migration(migrations.Migration):
    dependencies = [
        ("weblate_auth", "0008_userblock_note"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="TeamMembership",
                    fields=[
                        (
                            "id",
                            models.AutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "group",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="memberships",
                                to="weblate_auth.group",
                            ),
                        ),
                        (
                            "user",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="team_memberships",
                                to="weblate_auth.user",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Team membership",
                        "verbose_name_plural": "Team memberships",
                        "db_table": "weblate_auth_user_groups",
                        "constraints": [
                            # This is the historical auto-created M2M unique
                            # constraint name for User.groups on
                            # weblate_auth_user_groups. The migration keeps it
                            # in state only, so later migrations target the
                            # existing database constraint instead of trying to
                            # create a duplicate one.
                            models.UniqueConstraint(
                                fields=("user", "group"),
                                name="weblate_auth_user_groups_user_id_group_id_16cfc05b_uniq",
                            )
                        ],
                    },
                ),
                migrations.AlterField(
                    model_name="user",
                    name="groups",
                    field=weblate.auth.models.GroupManyToManyField(
                        blank=True,
                        help_text="The user is granted all permissions included in membership of these teams.",
                        through="weblate_auth.TeamMembership",
                        to="weblate_auth.group",
                        verbose_name="Teams",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="teammembership",
            name="limit_languages",
            field=models.ManyToManyField(
                blank=True,
                help_text="Limit permissions from this team to these languages. Project-wide, component-wide and global permissions from this team are not granted when a language limit is set. Empty selection uses the team language selection without additional limit.",
                to="lang.language",
                verbose_name="Limit languages",
            ),
        ),
    ]
