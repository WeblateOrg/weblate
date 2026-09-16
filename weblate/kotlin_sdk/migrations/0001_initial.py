# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("addons", "0022_addonactivitylog_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="KotlinSDKCleanup",
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
                ("path", models.TextField(unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="KotlinSDKArtifact",
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
                ("digest", models.CharField(max_length=64)),
                ("unreferenced", models.DateTimeField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name="KotlinSDKBuild",
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
                ("package_name", models.CharField(max_length=127)),
                ("version_code", models.PositiveBigIntegerField()),
                ("metadata", models.JSONField(default=dict)),
                ("pending_manifest", models.JSONField(default=dict)),
                ("digest", models.CharField(max_length=64)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("retired", models.DateTimeField(null=True)),
                ("status", models.CharField(default="pending", max_length=16)),
                ("error", models.TextField(blank=True)),
                ("published", models.DateTimeField(null=True)),
            ],
        ),
        migrations.AddField(
            model_name="kotlinsdkcleanup",
            name="build",
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cleanup",
                to="kotlin_sdk.kotlinsdkbuild",
            ),
        ),
        migrations.AddField(
            model_name="kotlinsdkartifact",
            name="addon",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sdk_artifacts",
                to="addons.addon",
            ),
        ),
        migrations.AddField(
            model_name="kotlinsdkbuild",
            name="addon",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sdk_builds",
                to="addons.addon",
            ),
        ),
        migrations.AddField(
            model_name="kotlinsdkartifact",
            name="builds",
            field=models.ManyToManyField(
                related_name="artifacts", to="kotlin_sdk.kotlinsdkbuild"
            ),
        ),
        migrations.AddConstraint(
            model_name="kotlinsdkbuild",
            constraint=models.UniqueConstraint(
                fields=("addon", "package_name", "version_code"),
                name="kotlin_sdk_build_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="kotlinsdkartifact",
            constraint=models.UniqueConstraint(
                fields=("addon", "digest"), name="kotlin_sdk_artifact_unique"
            ),
        ),
    ]
