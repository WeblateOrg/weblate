# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models.aggregates import Sum

from weblate.utils.query import conditional_sum


def fill_in_have_comment(apps, schema_editor):
    Translation = apps.get_model('trans', 'Translation')

    for translation in Translation.objects.all():
        stats = translation.unit_set.aggregate(
            Sum('num_words'),
            has_comment__sum=conditional_sum(1, has_comment=True),
        )
        if stats['num_words__sum'] is not None:
            translation.have_comment = int(stats['has_comment__sum'])
            translation.save()


class Migration(migrations.Migration):

    dependencies = [
        ('trans', '0012_translation_have_comment'),
    ]

    operations = [
        migrations.RunPython(fill_in_have_comment),
    ]
