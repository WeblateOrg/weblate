# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('code', models.SlugField(unique=True)),
                ('name', models.CharField(max_length=100)),
                ('nplurals', models.SmallIntegerField(default=0)),
                ('pluralequation', models.CharField(max_length=255, blank=True)),
                ('direction', models.CharField(default='ltr', max_length=3, choices=[('ltr', 'ltr'), ('rtl', 'rtl')])),
                ('plural_type', models.IntegerField(default=1, choices=[(0, 'None'), (1, 'One/other (classic plural)'), (2, 'One/few/other (Slavic languages)'), (3, 'Arabic languages'), (11, 'Zero/one/other'), (4, 'One/two/other'), (6, 'One/two/few/other'), (5, 'One/two/three/other'), (7, 'One/other/zero'), (8, 'One/few/many/other'), (9, 'Two/other'), (10, 'One/two/few/many/other'), (666, 'Unknown')])),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model,),
        ),
    ]
