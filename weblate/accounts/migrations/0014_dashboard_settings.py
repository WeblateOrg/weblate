# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0058_componentlist'),
        ('accounts', '0013_auto_20151222_1006'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='dashboard_component_list',
            field=models.ForeignKey(verbose_name='Default component list', blank=True, to='trans.ComponentList', null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='dashboard_view',
            field=models.CharField(default='your-subscriptions', max_length=100, verbose_name='Default dashboard view', choices=[('your-subscriptions', 'Your subscriptions'), ('your-languages', 'Your languages'), ('projects', 'All projects'), ('list', 'Component list')]),
        ),
        migrations.AlterField(
            model_name='profile',
            name='language',
            field=models.CharField(max_length=10, verbose_name='Interface Language', choices=[(b'az', 'Az\u0259rbaycan'), (b'be', '\u0411\u0435\u043b\u0430\u0440\u0443\u0441\u043a\u0430\u044f'), (b'be@latin', 'Bie\u0142aruskaja'), (b'br', 'Brezhoneg'), (b'ca', 'Catal\xe0'), (b'cs', '\u010ce\u0161tina'), (b'da', 'Dansk'), (b'de', 'Deutsch'), (b'en', 'English'), (b'el', '\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac'), (b'es', 'Espa\xf1ol'), (b'fi', 'Suomi'), (b'fr', 'Fran\xe7ais'), (b'fy', 'Frysk'), (b'gl', 'Galego'), (b'he', '\u05e2\u05d1\u05e8\u05d9\u05ea'), (b'hu', 'Magyar'), (b'id', b'Indonesia'), (b'ja', '\u65e5\u672c\u8a9e'), (b'ko', '\ud55c\uad6d\uc5b4'), (b'ksh', 'K\xf6lsch'), (b'nl', 'Nederlands'), (b'pl', 'Polski'), (b'pt', 'Portugu\xeas'), (b'pt-br', 'Portugu\xeas brasileiro'), (b'ru', '\u0420\u0443\u0441\u0441\u043a\u0438\u0439'), (b'sk', 'Sloven\u010dina'), (b'sl', 'Sloven\u0161\u010dina'), (b'sr', '\u0421\u0440\u043f\u0441\u043a\u0438'), (b'sv', 'Svenska'), (b'tr', 'T\xfcrk\xe7e'), (b'uk', '\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430'), (b'zh-hans', '\u7b80\u4f53\u5b57'), (b'zh-hant', '\u6b63\u9ad4\u5b57')]),
        ),
    ]
