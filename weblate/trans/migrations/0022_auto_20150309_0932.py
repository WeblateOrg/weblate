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
            field=models.CharField(default=b'auto', help_text='Automatic detection might fail for some formats and is slightly slower.', max_length=50, verbose_name='File format', choices=[(b'aresource', 'Android String Resource'), (b'auto', 'Automatic detection'), (b'json', 'JSON file'), (b'php', 'PHP strings'), (b'po', 'Gettext PO file'), (b'po-mono', 'Gettext PO file (monolingual)'), (b'properties', 'Java Properties'), (b'properties-utf8', 'Java Properties (UTF-8)'), (b'resx', '.Net resource file'), (b'strings', 'OS X Strings'), (b'strings-utf8', 'OS X Strings (UTF-8)'), (b'ts', 'Qt Linguist Translation File'), (b'xliff', 'XLIFF Translation File')]),
            preserve_default=True,
        ),
    ]
