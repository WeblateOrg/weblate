# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import weblate.trans.validators


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0042_auto_20150910_0854'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='extra_commit_file',
            field=models.TextField(default=b'', help_text='Additional files to include in commits, one per line; please check documentation for more details.', blank=True, verbose_name='Additional commit files', validators=[weblate.trans.validators.validate_extra_file]),
        ),
    ]
