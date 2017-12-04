# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0021_auto_20150306_1605'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='file_format',
            field=models.CharField(default='auto', help_text='Automatic detection might fail for some formats and is slightly slower.', max_length=50, verbose_name='File format', choices=[('aresource', 'Android String Resource'), ('auto', 'Automatic detection'), ('json', 'JSON file'), ('php', 'PHP strings'), ('po', 'Gettext PO file'), ('po-mono', 'Gettext PO file (monolingual)'), ('properties', 'Java Properties'), ('properties-utf8', 'Java Properties (UTF-8)'), ('resx', '.Net resource file'), ('strings', 'OS X Strings'), ('strings-utf8', 'OS X Strings (UTF-8)'), ('ts', 'Qt Linguist Translation File'), ('xliff', 'XLIFF Translation File')]),
            preserve_default=True,
        ),
    ]
