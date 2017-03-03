# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('trans', '0045_auto_20150916_1007'),
    ]

    operations = [
        migrations.CreateModel(
            name='Billing',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
        ),
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=100)),
                ('price', models.IntegerField()),
                ('limit_strings', models.IntegerField()),
                ('limit_languages', models.IntegerField()),
                ('limit_repositories', models.IntegerField()),
                ('limit_projects', models.IntegerField()),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='billing',
            name='plan',
            field=models.ForeignKey(to='billing.Plan'),
        ),
        migrations.AddField(
            model_name='billing',
            name='projects',
            field=models.ManyToManyField(to='trans.Project', blank=True),
        ),
        migrations.AddField(
            model_name='billing',
            name='user',
            field=models.OneToOneField(to=settings.AUTH_USER_MODEL),
        ),
    ]
