# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0023_project_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='edit_template',
            field=models.BooleanField(default=True, help_text='Whether users will be able to edit base file for monolingual translations.', verbose_name='Edit base file'),
            preserve_default=True,
        ),
    ]
