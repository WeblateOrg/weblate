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
                ('name', models.CharField(help_text='Name to display', unique=True, max_length=100, verbose_name='Component list name')),
                ('slug', models.SlugField(help_text='Name used in URLs and file names.', unique=True, max_length=100, verbose_name='URL slug')),
                ('components', models.ManyToManyField(to='trans.SubProject')),
            ],
            options={
                'verbose_name': 'Component list',
                'verbose_name_plural': 'Component lists',
            },
        ),
    ]
