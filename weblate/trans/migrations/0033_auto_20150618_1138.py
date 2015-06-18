# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0032_subproject_agreement'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='advertisement',
            options={'verbose_name': 'Advertisement', 'verbose_name_plural': 'Advertisements'},
        ),
        migrations.AlterModelOptions(
            name='project',
            options={'ordering': ['name'], 'verbose_name': 'Project', 'verbose_name_plural': 'Projects', 'permissions': (('manage_acl', 'Can manage ACL rules for a project'),)},
        ),
        migrations.AlterModelOptions(
            name='subproject',
            options={'ordering': ['project__name', 'name'], 'verbose_name': 'Component', 'verbose_name_plural': 'Components', 'permissions': (('lock_subproject', 'Can lock translation for translating'), ('can_see_git_repository', 'Can see VCS repository URL'))},
        ),
        migrations.AlterModelOptions(
            name='whiteboardmessage',
            options={'verbose_name': 'Whiteboard message', 'verbose_name_plural': 'Whiteboard messages'},
        ),
        migrations.AlterField(
            model_name='project',
            name='owner',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, help_text='Owner of the project.', null=True, verbose_name='Owner'),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='new_lang',
            field=models.CharField(default=b'contact', help_text='How to handle requests for creating new languages. Please note that availability of choices depends on the file format.', max_length=10, verbose_name='New language', choices=[(b'contact', 'Use contact form'), (b'url', 'Point to translation instructions URL'), (b'add', 'Automatically add language file'), (b'none', 'No adding of language')]),
        ),
    ]
