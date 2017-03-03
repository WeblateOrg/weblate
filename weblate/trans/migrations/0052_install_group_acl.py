# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lang', '0002_auto_20150630_1208'),
        ('trans', '0051_auto_20151222_1059'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupACL',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('groups', models.ManyToManyField(to='auth.Group')),
                ('language', models.ForeignKey(blank=True, to='lang.Language', null=True)),
                ('project', models.ForeignKey(blank=True, to='trans.Project', null=True)),
                ('subproject', models.ForeignKey(blank=True, to='trans.SubProject', null=True)),
            ],
            options={
                'verbose_name': 'Group ACL',
                'verbose_name_plural': 'Group ACLs',
            },
        ),
        migrations.AlterUniqueTogether(
            name='groupacl',
            unique_together=set([('project', 'subproject', 'language')]),
        ),
    ]
