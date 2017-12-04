# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('social_django', '0001_initial'),
        ('lang', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('language', models.CharField(max_length=10, verbose_name='Interface Language', choices=[('be', '\u0431\u0435\u043b\u0430\u0440\u0443\u0441\u043a\u0430\u044f'), ('br', 'Brezhoneg'), ('ca', 'Catal\xe0'), ('cs', '\u010cesky'), ('da', 'Dansk'), ('de', 'Deutsch'), ('en', 'English'), ('el', '\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac'), ('es', 'Espa\xf1ol'), ('fi', 'Suomi'), ('fr', 'Fran\xe7ais'), ('gl', 'Galego'), ('he', '\u05e2\u05b4\u05d1\u05b0\u05e8\u05b4\u05d9\u05ea'), ('hu', 'Magyar'), ('id', 'Indonesia'), ('ja', '\u65e5\u672c\u8a9e'), ('ko', '\ud55c\uad6d\uc5b4'), ('nl', 'Nederlands'), ('pl', 'Polski'), ('pt', 'Portugu\xeas'), ('pt_BR', 'Portugu\xeas brasileiro'), ('ru', '\u0440\u0443\u0441\u0441\u043a\u0438\u0439'), ('sk', 'Sloven\u010dina'), ('sl', 'Sloven\u0161\u010dina'), ('sv', 'Svenska'), ('tr', 'T\xfcrk\xe7e'), ('uk', '\u0443\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430 \u043c\u043e\u0432\u0430'), ('zh_CN', '\u7b80\u4f53\u5b57'), ('zh_TW', '\u6b63\u9ad4\u5b57')])),
                ('suggested', models.IntegerField(default=0, db_index=True)),
                ('translated', models.IntegerField(default=0, db_index=True)),
                ('subscribe_any_translation', models.BooleanField(default=False, verbose_name='Notification on any translation')),
                ('subscribe_new_string', models.BooleanField(default=False, verbose_name='Notification on new string to translate')),
                ('subscribe_new_suggestion', models.BooleanField(default=False, verbose_name='Notification on new suggestion')),
                ('subscribe_new_contributor', models.BooleanField(default=False, verbose_name='Notification on new contributor')),
                ('subscribe_new_comment', models.BooleanField(default=False, verbose_name='Notification on new comment')),
                ('subscribe_merge_failure', models.BooleanField(default=False, verbose_name='Notification on merge failure')),
                ('subscribe_new_language', models.BooleanField(default=False, verbose_name='Notification on new language request')),
                ('languages', models.ManyToManyField(to='lang.Language', verbose_name='Languages', blank=True)),
                ('secondary_languages', models.ManyToManyField(related_name='secondary_profile_set', verbose_name='Secondary languages', to='lang.Language', blank=True)),
                ('subscriptions', models.ManyToManyField(to='trans.Project', verbose_name='Subscribed projects')),
                ('user', models.OneToOneField(editable=False, to=settings.AUTH_USER_MODEL, on_delete=models.deletion.CASCADE)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='VerifiedEmail',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('email', models.EmailField(max_length=75)),

                ('social', models.ForeignKey(to='social_django.UserSocialAuth', on_delete=models.deletion.CASCADE)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
