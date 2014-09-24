# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import weblate.trans.mixins


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
                ('direction', models.CharField(default=b'ltr', max_length=3, choices=[(b'ltr', b'ltr'), (b'rtl', b'rtl')])),
                ('plural_type', models.IntegerField(default=1, choices=[(0, b'None'), (1, b'One/other (classic plural)'), (2, b'One/few/other (Slavic languages)'), (3, b'Arabic languages'), (11, b'Zero/one/other'), (4, b'One/two/other'), (6, b'One/two/few/other'), (5, b'One/two/three/other'), (7, b'One/other/zero'), (8, b'One/few/many/other'), (9, b'Two/other'), (10, b'One/two/few/many/other'), (666, b'Unknown')])),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model, weblate.trans.mixins.PercentMixin),
        ),
    ]
