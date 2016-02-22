# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_dashboard_settings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='dashboard_view',
            field=models.IntegerField(default=1, verbose_name='Default dashboard view', choices=[(1, 'Your subscriptions'), (2, 'Your languages'), (3, 'All projects'), (4, 'Component list')]),
        ),
        migrations.AlterField(
            model_name='profile',
            name='secondary_languages',
            field=models.ManyToManyField(help_text='Choose languages you can understand, strings in those languages will be shown in addition to the source string.', related_name='secondary_profile_set', verbose_name='Secondary languages', to='lang.Language', blank=True),
        ),
    ]
