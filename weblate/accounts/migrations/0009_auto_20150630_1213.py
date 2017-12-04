# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_profile_hide_source_secondary'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='language',
            field=models.CharField(max_length=10, verbose_name='Interface Language', choices=[('az', 'Az\u0259rbaycan'), ('be', '\u0411\u0435\u043b\u0430\u0440\u0443\u0441\u043a\u0430\u044f'), ('be@latin', 'Bie\u0142aruskaja'), ('br', 'Brezhoneg'), ('ca', 'Catal\xe0'), ('cs', '\u010ce\u0161tina'), ('da', 'Dansk'), ('de', 'Deutsch'), ('en', 'English'), ('el', '\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac'), ('es', 'Espa\xf1ol'), ('fi', 'Suomi'), ('fr', 'Fran\xe7ais'), ('fy', 'Frysk'), ('gl', 'Galego'), ('he', '\u05e2\u05d1\u05e8\u05d9\u05ea'), ('hu', 'Magyar'), ('id', 'Indonesia'), ('ja', '\u65e5\u672c\u8a9e'), ('ko', '\ud55c\uad6d\uc5b4'), ('ksh', 'K\xf6lsch'), ('nl', 'Nederlands'), ('pl', 'Polski'), ('pt', 'Portugu\xeas'), ('pt_BR', 'Portugu\xeas brasileiro'), ('ru', '\u0420\u0443\u0441\u0441\u043a\u0438\u0439'), ('sk', 'Sloven\u010dina'), ('sl', 'Sloven\u0161\u010dina'), ('sv', 'Svenska'), ('tr', 'T\xfcrk\xe7e'), ('uk', '\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430'), ('zh-Hans', '\u7b80\u4f53\u5b57'), ('zh-Hant', '\u6b63\u9ad4\u5b57')]),
        ),
    ]
