# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding unique constraint on 'SubProject', fields ['project', 'name']
        db.create_unique('trans_subproject', ['project_id', 'name'])

        # Adding unique constraint on 'SubProject', fields ['project', 'slug']
        db.create_unique('trans_subproject', ['project_id', 'slug'])

        # Adding unique constraint on 'Project', fields ['name']
        db.create_unique('trans_project', ['name'])

        # Adding unique constraint on 'Project', fields ['slug']
        db.create_unique('trans_project', ['slug'])


    def backwards(self, orm):
        # Removing unique constraint on 'Project', fields ['slug']
        db.delete_unique('trans_project', ['slug'])

        # Removing unique constraint on 'Project', fields ['name']
        db.delete_unique('trans_project', ['name'])

        # Removing unique constraint on 'SubProject', fields ['project', 'slug']
        db.delete_unique('trans_subproject', ['project_id', 'slug'])

        # Removing unique constraint on 'SubProject', fields ['project', 'name']
        db.delete_unique('trans_subproject', ['project_id', 'name'])


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
            'direction': ('django.db.models.fields.CharField', [], {'default': "'ltr'", 'max_length': '3'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'nplurals': ('django.db.models.fields.SmallIntegerField', [], {'default': '0'}),
            'pluralequation': ('django.db.models.fields.CharField', [], {'max_length': '255', 'blank': 'True'})
        },
        'trans.change': {
            'Meta': {'ordering': "['-timestamp']", 'object_name': 'Change'},
            'action': ('django.db.models.fields.IntegerField', [], {'default': '2'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'translation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Translation']"}),
            'unit': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Unit']", 'null': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'null': 'True'})
        },
        'trans.check': {
            'Meta': {'object_name': 'Check'},
            'check': ('django.db.models.fields.CharField', [], {'max_length': '20'}),
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'ignore': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']", 'null': 'True', 'blank': 'True'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"})
        },
        'trans.comment': {
            'Meta': {'ordering': "['timestamp']", 'object_name': 'Comment'},
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'comment': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']", 'null': 'True', 'blank': 'True'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'null': 'True', 'blank': 'True'})
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
            'source': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'unit': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Unit']"})
        },
        'trans.project': {
            'Meta': {'ordering': "['name']", 'object_name': 'Project'},
            'commit_message': ('django.db.models.fields.TextField', [], {'default': "'Translated using Weblate (%(language_name)s)\\n\\nCurrently translated at %(translated_percent)s%% (%(translated)s of %(total)s strings)'"}),
            'committer_email': ('django.db.models.fields.EmailField', [], {'default': "'noreply@weblate.org'", 'max_length': '75'}),
            'committer_name': ('django.db.models.fields.CharField', [], {'default': "'Weblate'", 'max_length': '200'}),
            'enable_acl': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'instructions': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'mail': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'merge_style': ('django.db.models.fields.CharField', [], {'default': "'merge'", 'max_length': '10'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'new_lang': ('django.db.models.fields.CharField', [], {'default': "'contact'", 'max_length': '10'}),
            'push_on_commit': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'set_translation_team': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '50'}),
            'web': ('django.db.models.fields.URLField', [], {'max_length': '200'})
        },
        'trans.subproject': {
            'Meta': {'ordering': "['project__name', 'name']", 'unique_together': "(('project', 'name'), ('project', 'slug'))", 'object_name': 'SubProject'},
            'allow_translation_propagation': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'branch': ('django.db.models.fields.CharField', [], {'default': "'master'", 'max_length': '50'}),
            'file_format': ('django.db.models.fields.CharField', [], {'default': "'auto'", 'max_length': '50'}),
            'filemask': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'locked': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'push': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            'repo': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'report_source_bugs': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'repoweb': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'template': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'})
        },
        'trans.suggestion': {
            'Meta': {'object_name': 'Suggestion'},
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']"}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'target': ('django.db.models.fields.TextField', [], {}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['auth.User']", 'null': 'True', 'blank': 'True'})
        },
        'trans.translation': {
            'Meta': {'ordering': "['language__name']", 'object_name': 'Translation'},
            'enabled': ('django.db.models.fields.BooleanField', [], {'default': 'True', 'db_index': 'True'}),
            'filename': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'fuzzy': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['lang.Language']"}),
            'language_code': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '20'}),
            'lock_time': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'lock_user': ('django.db.models.fields.related.ForeignKey', [], {'default': 'None', 'to': "orm['auth.User']", 'null': 'True', 'blank': 'True'}),
            'revision': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '100', 'blank': 'True'}),
            'subproject': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.SubProject']"}),
            'total': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'translated': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'})
        },
        'trans.unit': {
            'Meta': {'ordering': "['position']", 'object_name': 'Unit'},
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'comment': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'context': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'flags': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'fuzzy': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'location': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'position': ('django.db.models.fields.IntegerField', [], {'db_index': 'True'}),
            'previous_source': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'source': ('django.db.models.fields.TextField', [], {}),
            'target': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'translated': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'translation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Translation']"})
        }
    }

    complete_apps = ['trans']