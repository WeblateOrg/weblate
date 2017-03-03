# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0006_auto_20141021_1609'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='project',
            options={'ordering': ['name'], 'permissions': (('manage_acl', 'Can manage ACL rules for a project'),)},
        ),
    ]
