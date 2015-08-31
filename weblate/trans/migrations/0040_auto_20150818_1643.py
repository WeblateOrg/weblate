# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
import weblate.trans.fields


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0039_remove_project_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='language_regex',
            field=weblate.trans.fields.RegexField(default=b'^[^.]+$', help_text='Regular expression which is used to filter translation when scanning for file mask.', max_length=200, verbose_name='Language filter'),
        ),
    ]
