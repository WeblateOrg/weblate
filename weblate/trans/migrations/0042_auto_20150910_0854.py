# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


POST_ADD_SCRIPT_CHOICES = ()


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0041_auto_20150819_1457'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='post_add_script',
            field=models.CharField(default='', choices=POST_ADD_SCRIPT_CHOICES, max_length=200, blank=True, help_text='Script to be executed after adding new translation, please check documentation for more details.', verbose_name='Post-add script'),
        ),
    ]
