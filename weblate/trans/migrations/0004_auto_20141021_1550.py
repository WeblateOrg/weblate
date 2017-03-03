# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import weblate.trans.validators


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0003_auto_20141021_1348'),
    ]

    operations = [
        migrations.AddField(
            model_name='subproject',
            name='commit_message',
            field=models.TextField(default=b'Translated using Weblate (%(language_name)s)\n\nCurrently translated at %(translated_percent)s%% (%(translated)s of %(total)s strings)', help_text='You can use format strings for various information, please check documentation for more details.', verbose_name='Commit message', validators=[weblate.trans.validators.validate_commit_message]),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='committer_email',
            field=models.EmailField(default=b'noreply@weblate.org', max_length=75, verbose_name='Committer email'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='committer_name',
            field=models.CharField(default=b'Weblate', max_length=200, verbose_name='Committer name'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='license',
            field=models.CharField(default=b'', help_text='Optional short summary of license used for translations.', max_length=150, verbose_name='Translation license', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='license_url',
            field=models.URLField(default=b'', help_text='Optional URL with license details.', verbose_name='License URL', blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='merge_style',
            field=models.CharField(default=b'merge', help_text='Define whether Weblate should merge upstream repository or rebase changes onto it.', max_length=10, verbose_name='Merge style', choices=[(b'merge', 'Merge'), (b'rebase', 'Rebase')]),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subproject',
            name='new_lang',
            field=models.CharField(default=b'contact', help_text='How to handle requests for creating new languages.', max_length=10, verbose_name='New language', choices=[(b'contact', 'Use contact form'), (b'url', 'Point to translation instructions URL'), (b'add', 'Automatically add language file'), (b'none', 'No adding of language')]),
            preserve_default=True,
        ),
    ]
