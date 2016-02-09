# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_auto_20160208_1535'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='dashboard_view',
            field=models.CharField(default='your-subscriptions', max_length=100, verbose_name='Default dashboard view', choices=[('your-subscriptions', 'Your subscriptions'), ('your-languages', 'Your languages'), ('projects', 'All projects'), ('list', 'Component list')]),
        ),
    ]
