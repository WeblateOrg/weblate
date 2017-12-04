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
            field=models.CharField(default='auto', help_text='Automatic detection might fail for some formats and is slightly slower.', max_length=50, verbose_name='File format', choices=[('aresource', 'Android String Resource'), ('auto', 'Automatic detection'), ('csv', 'CSV file'), ('json', 'JSON file'), ('php', 'PHP strings'), ('po', 'Gettext PO file'), ('po-mono', 'Gettext PO file (monolingual)'), ('properties', 'Java Properties (ISO-8859-1)'), ('properties-utf16', 'Java Properties (UTF-16)'), ('properties-utf8', 'Java Properties (UTF-8)'), ('resx', '.Net resource file'), ('strings', 'OS X Strings'), ('strings-utf8', 'OS X Strings (UTF-8)'), ('ts', 'Qt Linguist Translation File'), ('xliff', 'XLIFF Translation File')]),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='new_lang',
            field=models.CharField(default='contact', help_text='How to handle requests for creating new translations. Please note that availability of choices depends on the file format.', max_length=10, verbose_name='New translation', choices=[('contact', 'Use contact form'), ('url', 'Point to translation instructions URL'), ('add', 'Automatically add language file'), ('none', 'No adding of language')]),
        ),
        migrations.AlterField(
            model_name='translation',
            name='language_code',
            field=models.CharField(default='', max_length=20, blank=True),
        ),
        migrations.AlterField(
            model_name='translation',
            name='lock_time',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
