# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0057_indexupdate_language_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='ComponentList',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=100)),
                ('components', models.ManyToManyField(to='trans.SubProject')),
            ],
            options={
                'verbose_name': 'Component list',
                'verbose_name_plural': 'Component lists',
            },
        ),
    ]
