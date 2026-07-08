# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0031_alter_auditlog_activity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subscription",
            name="notification",
            field=models.CharField(
                choices=[
                    (
                        "RepositoryNotification",
                        "Operation was performed in the repository",
                    ),
                    ("LockNotification", "Component was locked or unlocked"),
                    ("LicenseNotification", "License was changed"),
                    ("ParseErrorNotification", "Parse error occurred"),
                    ("NewStringNotificaton", "String is available for translation"),
                    (
                        "TranslationActivitySummaryNotification",
                        "Translation activity summary",
                    ),
                    (
                        "NewContributorNotificaton",
                        "Contributor made their first translation",
                    ),
                    ("NewSuggestionNotificaton", "Suggestion was added"),
                    ("LanguageTranslatedNotificaton", "Language was translated"),
                    ("ComponentTranslatedNotificaton", "Component was translated"),
                    ("NewCommentNotificaton", "Comment was added"),
                    ("MentionCommentNotificaton", "You were mentioned in a comment"),
                    (
                        "LastAuthorCommentNotificaton",
                        "String you contributed to received a comment",
                    ),
                    ("TranslatedStringNotificaton", "String was edited by user"),
                    ("ApprovedStringNotificaton", "String was approved"),
                    ("ChangedStringNotificaton", "String was changed"),
                    (
                        "NewTranslationNotificaton",
                        "New language was added or requested",
                    ),
                    (
                        "NewComponentNotificaton",
                        "New translation component was created",
                    ),
                    ("NewAnnouncementNotificaton", "Announcement was published"),
                    ("NewAlertNotificaton", "New alert emerged in a component"),
                    ("MergeFailureNotification", "Repository operation failed"),
                    ("PendingSuggestionsNotification", "Pending suggestions exist"),
                    ("ToDoStringsNotification", "Unfinished strings exist"),
                ],
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name="profile",
            name="auto_watch",
            field=models.BooleanField(
                default=True,
                help_text="Projects are added to your watched projects when you contribute to them.",
                verbose_name="Automatically watch projects on contribution",
            ),
        ),
    ]
