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
            field=models.CharField(max_length=20, choices=[(b'end_space', 'Trailing space'), (b'begin_space', 'Starting spaces'), (b'bbcode', 'Mismatched BBcode'), (b'python_brace_format', 'Python brace format'), (b'plurals', 'Missing plurals'), (b'escaped_newline', 'Mismatched \\n'), (b'end_exclamation', 'Trailing exclamation'), (b'php_format', 'PHP format'), (b'same', 'Unchanged translation'), (b'xml-tags', 'XML tags mismatch'), (b'inconsistent', 'Inconsistent'), (b'zero-width-space', 'Zero-width space'), (b'c_format', 'C format'), (b'end_colon', 'Trailing colon'), (b'end_question', 'Trailing question'), (b'end_ellipsis', 'Trailing ellipsis'), (b'end_stop', 'Trailing stop'), (b'begin_newline', 'Starting newline'), (b'javascript_format', 'Javascript format'), (b'end_newline', 'Trailing newline'), (b'python_format', 'Python format')]),
        ),
    ]
