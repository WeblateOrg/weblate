# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0059_auto_20160205_1349'),
        ('accounts', '0014_auto_20160205_1349'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='dashboard_component_list',
            field=models.ForeignKey(verbose_name='Default component list', blank=True, to='trans.ComponentList', null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='dashboard_view',
            field=models.IntegerField(default=0, verbose_name='Default dashboard view'),
        ),
    ]
