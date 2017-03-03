# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0031_auto_20150415_1339'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='agreement',
            field=models.TextField(default=b'', help_text='Agreement which needs to be approved before user can translate this component.', verbose_name='Contributor agreement', blank=True),
        ),
    ]
