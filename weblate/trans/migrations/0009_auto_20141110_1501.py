# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0008_auto_20141104_1200'),
    ]

    operations = [
        migrations.AlterField(
            model_name='check',
            name='check',
            field=models.CharField(max_length=20, choices=[(b'end_space', 'Trailing space'), (b'inconsistent', 'Inconsistent'), (b'begin_newline', 'Starting newline'), (b'zero-width-space', 'Zero-width space'), (b'escaped_newline', 'Mismatched \\n'), (b'same', 'Unchanged translation'), (b'end_question', 'Trailing question'), (b'end_ellipsis', 'Trailing ellipsis'), (b'ellipsis', 'Ellipsis'), (b'python_brace_format', 'Python brace format'), (b'end_newline', 'Trailing newline'), (b'c_format', 'C format'), (b'optional_plural', 'Optional plural'), (b'end_exclamation', 'Trailing exclamation'), (b'end_colon', 'Trailing colon'), (b'xml-tags', 'XML tags mismatch'), (b'python_format', 'Python format'), (b'plurals', 'Missing plurals'), (b'begin_space', 'Starting spaces'), (b'bbcode', 'Mismatched BBcode'), (b'multiple_failures', 'Multiple failing checks'), (b'php_format', 'PHP format'), (b'end_stop', 'Trailing stop')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='allow_translation_propagation',
            field=models.BooleanField(default=True, help_text='Whether translation updates in other components will cause automatic translation in this one', verbose_name='Allow translation propagation'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='branch',
            field=models.CharField(default=b'master', help_text='Repository branch to translate', max_length=50, verbose_name='Repository branch'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='git_export',
            field=models.CharField(help_text='URL of a repository where users can fetch changes from Weblate', max_length=200, verbose_name='Exported repository URL', blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='locked',
            field=models.BooleanField(default=False, help_text='Whether component is locked for translation updates.', verbose_name='Locked'),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='push',
            field=models.CharField(help_text='URL of a push repository, pushing is disabled if empty.', max_length=200, verbose_name='Repository push URL', blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subproject',
            name='repo',
            field=models.CharField(help_text='URL of a repository, use weblate://project/component for sharing with other component.', max_length=200, verbose_name='Source code repository'),
            preserve_default=True,
        ),
    ]
