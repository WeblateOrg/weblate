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
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):

    depends_on = (
        ('lang', '0001_initial'),
    )

    def forwards(self, orm):
        # Adding model 'Project'
        db.create_table('trans_project', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50)),
            ('web', self.gf('django.db.models.fields.URLField')(max_length=200)),
            ('mail', self.gf('django.db.models.fields.EmailField')(max_length=75, blank=True)),
            ('instructions', self.gf('django.db.models.fields.URLField')(max_length=200, blank=True)),
        ))
        db.send_create_signal('trans', ['Project'])

        # Adding model 'SubProject'
        db.create_table('trans_subproject', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50)),
            ('project', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Project'])),
            ('repo', self.gf('django.db.models.fields.CharField')(max_length=200)),
            ('push', self.gf('django.db.models.fields.CharField')(max_length=200, blank=True)),
            ('repoweb', self.gf('django.db.models.fields.URLField')(max_length=200, blank=True)),
            ('branch', self.gf('django.db.models.fields.CharField')(max_length=50)),
            ('filemask', self.gf('django.db.models.fields.CharField')(max_length=200)),
            ('template', self.gf('django.db.models.fields.CharField')(max_length=200, blank=True)),
        ))
        db.send_create_signal('trans', ['SubProject'])

        # Adding model 'Translation'
        db.create_table('trans_translation', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('subproject', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.SubProject'])),
            ('language', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['lang.Language'])),
            ('revision', self.gf('django.db.models.fields.CharField')(default='', max_length=40, blank=True)),
            ('filename', self.gf('django.db.models.fields.CharField')(max_length=200)),
            ('translated', self.gf('django.db.models.fields.IntegerField')(default=0, db_index=True)),
            ('fuzzy', self.gf('django.db.models.fields.IntegerField')(default=0, db_index=True)),
            ('total', self.gf('django.db.models.fields.IntegerField')(default=0, db_index=True)),
        ))
        db.send_create_signal('trans', ['Translation'])

        # Adding model 'Unit'
        db.create_table('trans_unit', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('translation', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Translation'])),
            ('checksum', self.gf('django.db.models.fields.CharField')(default='', max_length=40, db_index=True, blank=True)),
            ('location', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('context', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('comment', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('flags', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('source', self.gf('django.db.models.fields.TextField')()),
            ('target', self.gf('django.db.models.fields.TextField')(default='', blank=True)),
            ('fuzzy', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
            ('translated', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
            ('position', self.gf('django.db.models.fields.IntegerField')(db_index=True)),
        ))
        db.send_create_signal('trans', ['Unit'])

        # Adding model 'Suggestion'
        db.create_table('trans_suggestion', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('checksum', self.gf('django.db.models.fields.CharField')(default='', max_length=40, db_index=True, blank=True)),
            ('target', self.gf('django.db.models.fields.TextField')()),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['auth.User'], null=True, blank=True)),
            ('project', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Project'])),
            ('language', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['lang.Language'])),
        ))
        db.send_create_signal('trans', ['Suggestion'])

        # Adding model 'Check'
        db.create_table('trans_check', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('checksum', self.gf('django.db.models.fields.CharField')(default='', max_length=40, db_index=True, blank=True)),
            ('project', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Project'])),
            ('language', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['lang.Language'])),
            ('check', self.gf('django.db.models.fields.CharField')(max_length=20)),
            ('ignore', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
        ))
        db.send_create_signal('trans', ['Check'])

        # Adding model 'Dictionary'
        db.create_table('trans_dictionary', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('project', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Project'])),
            ('language', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['lang.Language'])),
            ('source', self.gf('django.db.models.fields.CharField')(max_length=200, db_index=True)),
            ('target', self.gf('django.db.models.fields.CharField')(max_length=200)),
        ))
        db.send_create_signal('trans', ['Dictionary'])

        # Adding model 'Change'
        db.create_table('trans_change', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('unit', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Unit'])),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['auth.User'])),
            ('timestamp', self.gf('django.db.models.fields.DateTimeField')(auto_now_add=True, db_index=True, blank=True)),
        ))
        db.send_create_signal('trans', ['Change'])

        # Adding model 'IndexUpdate'
        db.create_table('trans_indexupdate', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('unit', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['trans.Unit'])),
        ))
        db.send_create_signal('trans', ['IndexUpdate'])


    def backwards(self, orm):
        # Deleting model 'Project'
        db.delete_table('trans_project')

        # Deleting model 'SubProject'
        db.delete_table('trans_subproject')

        # Deleting model 'Translation'
        db.delete_table('trans_translation')

        # Deleting model 'Unit'
        db.delete_table('trans_unit')

        # Deleting model 'Suggestion'
        db.delete_table('trans_suggestion')

        # Deleting model 'Check'
        db.delete_table('trans_check')

        # Deleting model 'Dictionary'
        db.delete_table('trans_dictionary')

        # Deleting model 'Change'
        db.delete_table('trans_change')

        # Deleting model 'IndexUpdate'
        db.delete_table('trans_indexupdate')


    models = {
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'lang.language': {
            'Meta': {'ordering': "['name']", 'object_name': 'Language'},
            'code': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '50'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'nplurals': ('django.db.models.fields.SmallIntegerField', [], {'default': '0'}),
            'pluralequation': ('django.db.models.fields.CharField', [], {'max_length': '255', 'blank': 'True'})
        },
        'trans.change': {
            'Meta': {'ordering': "['-timestamp']", 'object_name': 'Change'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'unit': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Unit']"}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']"})
        },
        'trans.check': {
            'Meta': {'object_name': 'Check'},
            'check': ('django.db.models.fields.CharField', [], {'max_length': '20'}),
            'checksum': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '40', 'db_index': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'ignore': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']"}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"})
        },
        'trans.dictionary': {
            'Meta': {'ordering': "['source']", 'object_name': 'Dictionary'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']"}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '200', 'db_index': 'True'}),
            'target': ('django.db.models.fields.CharField', [], {'max_length': '200'})
        },
        'trans.indexupdate': {
            'Meta': {'object_name': 'IndexUpdate'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'unit': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Unit']"})
        },
        'trans.project': {
            'Meta': {'ordering': "['name']", 'object_name': 'Project'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'instructions': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'mail': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'web': ('django.db.models.fields.URLField', [], {'max_length': '200'})
        },
        'trans.subproject': {
            'Meta': {'ordering': "['name']", 'object_name': 'SubProject'},
            'branch': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'filemask': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'push': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            'repo': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'repoweb': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'template': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'})
        },
        'trans.suggestion': {
            'Meta': {'object_name': 'Suggestion'},
            'checksum': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '40', 'db_index': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']"}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'target': ('django.db.models.fields.TextField', [], {}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'null': 'True', 'blank': 'True'})
        },
        'trans.translation': {
            'Meta': {'ordering': "['language__name']", 'object_name': 'Translation'},
            'filename': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'fuzzy': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']"}),
            'revision': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '40', 'blank': 'True'}),
            'subproject': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.SubProject']"}),
            'total': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'translated': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'})
        },
        'trans.unit': {
            'Meta': {'ordering': "['position']", 'object_name': 'Unit'},
            'checksum': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '40', 'db_index': 'True', 'blank': 'True'}),
            'comment': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'context': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'flags': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'fuzzy': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'location': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'position': ('django.db.models.fields.IntegerField', [], {'db_index': 'True'}),
            'source': ('django.db.models.fields.TextField', [], {}),
            'target': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'translated': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'translation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Translation']"})
        }
    }

    complete_apps = ['trans']
