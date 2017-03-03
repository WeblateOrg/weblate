# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import weblate.trans.validators


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0010_source_check_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='vcs',
            field=models.CharField(default=b'git', help_text='Version control system to use to access your repository with translations.', max_length=20, verbose_name='Version control system', choices=[(b'git', b'Git'), (b'mercurial', b'Mercurial')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='source',
            name='check_flags',
            field=models.TextField(default=b'', blank=True, validators=[weblate.trans.validators.validate_check_flags]),
            preserve_default=True,
        ),
    ]
