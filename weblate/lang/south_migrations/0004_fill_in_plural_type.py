# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from south.v2 import DataMigration
from weblate.lang.models import get_plural_type


class Migration(DataMigration):

    def forwards(self, orm):
        "Write your forwards methods here."
        for lang in orm.Language.objects.all():
            # Cleanup plural equation
            if lang.pluralequation[-1] == ';':
                lang.pluralequation = lang.pluralequation[:-1]
            if lang.pluralequation[0] == '(' and lang.pluralequation[-1] == ')':
                lang.pluralequation = lang.pluralequation[1:-1]

            # Add plural type
            lang.plural_type = get_plural_type(
                lang.code,
                lang.pluralequation
            )

            lang.save()

    def backwards(self, orm):
        "Write your backwards methods here."

    models = {
        'lang.language': {
            'Meta': {'ordering': "['name']", 'object_name': 'Language'},
            'code': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '50'}),
            'direction': ('django.db.models.fields.CharField', [], {'default': "'ltr'", 'max_length': '3'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'nplurals': ('django.db.models.fields.SmallIntegerField', [], {'default': '0'}),
            'plural_type': ('django.db.models.fields.IntegerField', [], {'default': '1'}),
            'pluralequation': ('django.db.models.fields.CharField', [], {'max_length': '255', 'blank': 'True'})
        }
    }

    complete_apps = ['lang']
    symmetrical = True
