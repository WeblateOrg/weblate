# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0018_auto_20150213_1447'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='vcs',
            field=models.CharField(default=b'git', help_text='Version control system to use to access your repository with translations.', max_length=20, verbose_name='Version control system', choices=[(b'git', b'Git'), (b'gerrit', b'Gerrit'), (b'mercurial', b'Mercurial')]),
            preserve_default=True,
        ),
    ]
