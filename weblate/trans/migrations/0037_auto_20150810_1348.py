# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('trans', '0036_auto_20150709_1005'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='owners',
            field=models.ManyToManyField(help_text='Owners of the project.', to=settings.AUTH_USER_MODEL, verbose_name='Owners', blank=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='owner',
            field=models.ForeignKey(related_name='old_owned_projects', blank=True, to=settings.AUTH_USER_MODEL, help_text='Owner of the project.', null=True, verbose_name='Owner'),
        ),
    ]
