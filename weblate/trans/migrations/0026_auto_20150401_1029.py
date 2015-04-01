# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0025_subproject_post_update_script'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='post_update_script',
            field=models.CharField(default=b'', choices=[(b'', b'')], max_length=200, blank=True, help_text='Script to be executed after receiving a repository update, please check documentation for more details.', verbose_name='Post-update script'),
            preserve_default=True,
        ),
    ]
