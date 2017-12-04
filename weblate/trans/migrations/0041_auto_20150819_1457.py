# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0040_auto_20150818_1643'),
    ]

    operations = [
        migrations.AlterField(
            model_name='check',
            name='check',
            field=models.CharField(max_length=20, choices=[('end_space', 'Trailing space'), ('begin_space', 'Starting spaces'), ('bbcode', 'Mismatched BBcode'), ('python_brace_format', 'Python brace format'), ('plurals', 'Missing plurals'), ('escaped_newline', 'Mismatched \\n'), ('end_exclamation', 'Trailing exclamation'), ('php_format', 'PHP format'), ('same', 'Unchanged translation'), ('xml-tags', 'XML tags mismatch'), ('inconsistent', 'Inconsistent'), ('zero-width-space', 'Zero-width space'), ('c_format', 'C format'), ('end_colon', 'Trailing colon'), ('end_question', 'Trailing question'), ('end_ellipsis', 'Trailing ellipsis'), ('end_stop', 'Trailing stop'), ('begin_newline', 'Starting newline'), ('javascript_format', 'Javascript format'), ('end_newline', 'Trailing newline'), ('python_format', 'Python format')]),
        ),
    ]
