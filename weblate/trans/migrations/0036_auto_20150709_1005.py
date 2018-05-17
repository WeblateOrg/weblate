# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

POST_COMMIT_SCRIPT_CHOICES = ()
POST_PUSH_SCRIPT_CHOICES = ()


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0035_auto_20150630_1208'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='post_commit_script',
            field=models.CharField(default='', choices=POST_COMMIT_SCRIPT_CHOICES, max_length=200, blank=True, help_text='Script to be executed after committing translation, please check documentation for more details.', verbose_name='Post-commit script'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='post_push_script',
            field=models.CharField(default='', choices=POST_PUSH_SCRIPT_CHOICES, max_length=200, blank=True, help_text='Script to be executed after pushing translation to remote, please check documentation for more details.', verbose_name='Post-push script'),
            preserve_default=True,
        ),
    ]
