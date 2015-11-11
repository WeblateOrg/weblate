# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0045_auto_20150916_1007'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='subproject',
            options={'ordering': ['project__name', 'name'], 'verbose_name': 'Component', 'verbose_name_plural': 'Components', 'permissions': (('lock_subproject', 'Can lock translation for translating'), ('can_see_git_repository', 'Can see VCS repository URL'), ('view_reports', 'Can display reports'))},
        ),
        migrations.AlterField(
            model_name='subproject',
            name='file_format',
            field=models.CharField(default=b'auto', help_text='Automatic detection might fail for some formats and is slightly slower.', max_length=50, verbose_name='File format', choices=[(b'aresource', 'Android String Resource'), (b'auto', 'Automatic detection'), (b'csv', 'CSV file'), (b'json', 'JSON file'), (b'php', 'PHP strings'), (b'po', 'Gettext PO file'), (b'po-mono', 'Gettext PO file (monolingual)'), (b'properties', 'Java Properties (ISO-8859-1)'), (b'properties-utf16', 'Java Properties (UTF-16)'), (b'properties-utf8', 'Java Properties (UTF-8)'), (b'resx', '.Net resource file'), (b'strings', 'OS X Strings'), (b'strings-utf8', 'OS X Strings (UTF-8)'), (b'ts', 'Qt Linguist Translation File'), (b'xliff', 'XLIFF Translation File')]),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='new_lang',
            field=models.CharField(default=b'contact', help_text='How to handle requests for creating new translations. Please note that availability of choices depends on the file format.', max_length=10, verbose_name='New translation', choices=[(b'contact', 'Use contact form'), (b'url', 'Point to translation instructions URL'), (b'add', 'Automatically add language file'), (b'none', 'No adding of language')]),
        ),
        migrations.AlterField(
            model_name='translation',
            name='language_code',
            field=models.CharField(default=b'', max_length=20, blank=True),
        ),
        migrations.AlterField(
            model_name='translation',
            name='lock_time',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
