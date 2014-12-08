# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0015_auto_20141203_1345'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='subproject',
            options={'ordering': ['project__name', 'name'], 'permissions': (('lock_subproject', 'Can lock translation for translating'), ('can_see_git_repository', 'Can see VCS repository URL'))},
        ),
        migrations.AlterModelOptions(
            name='translation',
            options={'ordering': ['language__name'], 'permissions': (('upload_translation', 'Can upload translation'), ('overwrite_translation', 'Can overwrite with translation upload'), ('author_translation', 'Can define author of translation upload'), ('commit_translation', 'Can force commiting of translation'), ('update_translation', 'Can update translation from VCS'), ('push_translation', 'Can push translations to remote VCS'), ('reset_translation', 'Can reset translations to match remote VCS'), ('automatic_translation', 'Can do automatic translation'), ('lock_translation', 'Can lock whole translation project'), ('use_mt', 'Can use machine translation'))},
        ),
    ]
