# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import weblate.trans.validators


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0009_auto_20141110_1501'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='check_flags',
            field=models.TextField(default=b'', help_text='Additional comma-separated flags to influence quality checks, check documentation for possible values.', blank=True, verbose_name='Quality checks flags', validators=[weblate.trans.validators.validate_check_flags]),
            preserve_default=True,
        ),
    ]
