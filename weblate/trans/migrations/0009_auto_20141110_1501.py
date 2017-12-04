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
            field=models.CharField(max_length=20, choices=[('end_space', 'Trailing space'), ('inconsistent', 'Inconsistent'), ('begin_newline', 'Starting newline'), ('zero-width-space', 'Zero-width space'), ('escaped_newline', 'Mismatched \\n'), ('same', 'Unchanged translation'), ('end_question', 'Trailing question'), ('end_ellipsis', 'Trailing ellipsis'), ('ellipsis', 'Ellipsis'), ('python_brace_format', 'Python brace format'), ('end_newline', 'Trailing newline'), ('c_format', 'C format'), ('optional_plural', 'Optional plural'), ('end_exclamation', 'Trailing exclamation'), ('end_colon', 'Trailing colon'), ('xml-tags', 'XML tags mismatch'), ('python_format', 'Python format'), ('plurals', 'Missing plurals'), ('begin_space', 'Starting spaces'), ('bbcode', 'Mismatched BBcode'), ('multiple_failures', 'Multiple failing checks'), ('php_format', 'PHP format'), ('end_stop', 'Trailing stop')]),
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
            field=models.CharField(default='master', help_text='Repository branch to translate', max_length=50, verbose_name='Repository branch'),
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
