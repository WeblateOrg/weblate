# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0016_auto_20141208_1029'),
    ]

    operations = [
        migrations.AlterField(
            model_name='check',
            name='check',
            field=models.CharField(max_length=20, choices=[(b'end_space', 'Trailing space'), (b'begin_space', 'Starting spaces'), (b'python_brace_format', 'Python brace format'), (b'plurals', 'Missing plurals'), (b'escaped_newline', 'Mismatched \\n'), (b'end_exclamation', 'Trailing exclamation'), (b'php_format', 'PHP format'), (b'same', 'Unchanged translation'), (b'xml-tags', 'XML tags mismatch'), (b'bbcode', 'Mismatched BBcode'), (b'zero-width-space', 'Zero-width space'), (b'c_format', 'C format'), (b'end_colon', 'Trailing colon'), (b'end_question', 'Trailing question'), (b'end_ellipsis', 'Trailing ellipsis'), (b'end_stop', 'Trailing stop'), (b'begin_newline', 'Starting newline'), (b'inconsistent', 'Inconsistent'), (b'end_newline', 'Trailing newline'), (b'python_format', 'Python format')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='project',
            name='mail',
            field=models.EmailField(help_text='Mailing list for translators.', max_length=254, verbose_name='Mailing list', blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='committer_email',
            field=models.EmailField(default=b'noreply@weblate.org', max_length=254, verbose_name='Committer email'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='report_source_bugs',
            field=models.EmailField(help_text='Email address where errors in source string will be reported, keep empty for no emails.', max_length=254, verbose_name='Source string bug report address', blank=True),
            preserve_default=True,
        ),
    ]
