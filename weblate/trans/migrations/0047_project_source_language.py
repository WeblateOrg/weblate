# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import weblate.lang.models


class Migration(migrations.Migration):

    dependencies = [
        ('lang', '0002_auto_20150630_1208'),
        ('trans', '0046_auto_20151111_1456'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='source_language',
            field=models.ForeignKey(default=weblate.lang.models.get_english_lang, verbose_name='Source language', to='lang.Language', help_text='Language used for source strings in all components'),
        ),
    ]
