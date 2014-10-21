# -*- coding: utf-8 -*-
from south.db import db
from south.v2 import SchemaMigration


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding field 'SubProject.license'
        db.add_column(u'trans_subproject', 'license',
                      self.gf('django.db.models.fields.CharField')(default='', max_length=150, blank=True),
                      keep_default=False)

        # Adding field 'SubProject.license_url'
        db.add_column(u'trans_subproject', 'license_url',
                      self.gf('django.db.models.fields.URLField')(default='', max_length=200, blank=True),
                      keep_default=False)

        # Adding field 'SubProject.new_lang'
        db.add_column(u'trans_subproject', 'new_lang',
                      self.gf('django.db.models.fields.CharField')(default='contact', max_length=10),
                      keep_default=False)

        # Adding field 'SubProject.merge_style'
        db.add_column(u'trans_subproject', 'merge_style',
                      self.gf('django.db.models.fields.CharField')(default='merge', max_length=10),
                      keep_default=False)

        # Adding field 'SubProject.commit_message'
        db.add_column(u'trans_subproject', 'commit_message',
                      self.gf('django.db.models.fields.TextField')(default='Translated using Weblate (%(language_name)s)\n\nCurrently translated at %(translated_percent)s%% (%(translated)s of %(total)s strings)'),
                      keep_default=False)

        # Adding field 'SubProject.committer_name'
        db.add_column(u'trans_subproject', 'committer_name',
                      self.gf('django.db.models.fields.CharField')(default='Weblate', max_length=200),
                      keep_default=False)

        # Adding field 'SubProject.committer_email'
        db.add_column(u'trans_subproject', 'committer_email',
                      self.gf('django.db.models.fields.EmailField')(default='noreply@weblate.org', max_length=75),
                      keep_default=False)


    def backwards(self, orm):
        # Deleting field 'SubProject.license'
        db.delete_column(u'trans_subproject', 'license')

        # Deleting field 'SubProject.license_url'
        db.delete_column(u'trans_subproject', 'license_url')

        # Deleting field 'SubProject.new_lang'
        db.delete_column(u'trans_subproject', 'new_lang')

        # Deleting field 'SubProject.merge_style'
        db.delete_column(u'trans_subproject', 'merge_style')

        # Deleting field 'SubProject.commit_message'
        db.delete_column(u'trans_subproject', 'commit_message')

        # Deleting field 'SubProject.committer_name'
        db.delete_column(u'trans_subproject', 'committer_name')

        # Deleting field 'SubProject.committer_email'
        db.delete_column(u'trans_subproject', 'committer_email')


    models = {
        u'auth.group': {
            'Meta': {'object_name': 'Group'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'auth.permission': {
            'Meta': {'ordering': "(u'content_type__app_label', u'content_type__model', u'codename')", 'unique_together': "((u'content_type', u'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        u'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Group']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Permission']"}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        u'lang.language': {
            'Meta': {'ordering': "['name']", 'object_name': 'Language'},
            'code': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '50'}),
            'direction': ('django.db.models.fields.CharField', [], {'default': "'ltr'", 'max_length': '3'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'nplurals': ('django.db.models.fields.SmallIntegerField', [], {'default': '0'}),
            'plural_type': ('django.db.models.fields.IntegerField', [], {'default': '1'}),
            'pluralequation': ('django.db.models.fields.CharField', [], {'max_length': '255', 'blank': 'True'})
        },
        'trans.advertisement': {
            'Meta': {'object_name': 'Advertisement', 'index_together': "[('placement', 'date_start', 'date_end')]"},
            'date_end': ('django.db.models.fields.DateField', [], {}),
            'date_start': ('django.db.models.fields.DateField', [], {}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'note': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'placement': ('django.db.models.fields.IntegerField', [], {}),
            'text': ('django.db.models.fields.TextField', [], {})
        },
        'trans.change': {
            'Meta': {'ordering': "['-timestamp']", 'object_name': 'Change'},
            'action': ('django.db.models.fields.IntegerField', [], {'default': '2'}),
            'author': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'author_set'", 'null': 'True', 'to': u"orm['auth.User']"}),
            'dictionary': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Dictionary']", 'null': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'target': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'translation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Translation']", 'null': 'True'}),
            'unit': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Unit']", 'null': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['auth.User']", 'null': 'True'})
        },
        'trans.check': {
            'Meta': {'unique_together': "(('contentsum', 'project', 'language', 'check'),)", 'object_name': 'Check'},
            'check': ('django.db.models.fields.CharField', [], {'max_length': '20'}),
            'contentsum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'ignore': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['lang.Language']", 'null': 'True', 'blank': 'True'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"})
        },
        'trans.comment': {
            'Meta': {'ordering': "['timestamp']", 'object_name': 'Comment'},
            'comment': ('django.db.models.fields.TextField', [], {}),
            'contentsum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['lang.Language']", 'null': 'True', 'blank': 'True'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'db_index': 'True', 'blank': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['auth.User']", 'null': 'True', 'blank': 'True'})
        },
        'trans.dictionary': {
            'Meta': {'ordering': "['source']", 'object_name': 'Dictionary'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['lang.Language']"}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'source': ('django.db.models.fields.CharField', [], {'max_length': '200', 'db_index': 'True'}),
            'target': ('django.db.models.fields.CharField', [], {'max_length': '200'})
        },
        'trans.indexupdate': {
            'Meta': {'object_name': 'IndexUpdate'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'source': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'unit': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Unit']", 'unique': 'True'})
        },
        'trans.project': {
            'Meta': {'ordering': "['name']", 'object_name': 'Project'},
            'commit_message': ('django.db.models.fields.TextField', [], {'default': "'Translated using Weblate (%(language_name)s)\\n\\nCurrently translated at %(translated_percent)s%% (%(translated)s of %(total)s strings)'"}),
            'committer_email': ('django.db.models.fields.EmailField', [], {'default': "'noreply@weblate.org'", 'max_length': '75'}),
            'committer_name': ('django.db.models.fields.CharField', [], {'default': "'Weblate'", 'max_length': '200'}),
            'enable_acl': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'enable_hooks': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'instructions': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'license': ('django.db.models.fields.CharField', [], {'max_length': '150', 'blank': 'True'}),
            'license_url': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'mail': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'merge_style': ('django.db.models.fields.CharField', [], {'default': "'merge'", 'max_length': '10'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'new_lang': ('django.db.models.fields.CharField', [], {'default': "'contact'", 'max_length': '10'}),
            'push_on_commit': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'set_translation_team': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'unique': 'True', 'max_length': '50'}),
            'web': ('django.db.models.fields.URLField', [], {'max_length': '200'})
        },
        'trans.source': {
            'Meta': {'unique_together': "(('checksum', 'subproject'),)", 'object_name': 'Source'},
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '40'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'priority': ('django.db.models.fields.IntegerField', [], {'default': '100'}),
            'subproject': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.SubProject']"}),
            'timestamp': ('django.db.models.fields.DateTimeField', [], {'auto_now_add': 'True', 'blank': 'True'})
        },
        'trans.subproject': {
            'Meta': {'ordering': "['project__name', 'name']", 'unique_together': "(('project', 'name'), ('project', 'slug'))", 'object_name': 'SubProject'},
            'allow_translation_propagation': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'branch': ('django.db.models.fields.CharField', [], {'default': "'master'", 'max_length': '50'}),
            'check_flags': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'commit_message': ('django.db.models.fields.TextField', [], {'default': "'Translated using Weblate (%(language_name)s)\\n\\nCurrently translated at %(translated_percent)s%% (%(translated)s of %(total)s strings)'"}),
            'committer_email': ('django.db.models.fields.EmailField', [], {'default': "'noreply@weblate.org'", 'max_length': '75'}),
            'committer_name': ('django.db.models.fields.CharField', [], {'default': "'Weblate'", 'max_length': '200'}),
            'enable_suggestions': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'extra_commit_file': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '200', 'blank': 'True'}),
            'file_format': ('django.db.models.fields.CharField', [], {'default': "'auto'", 'max_length': '50'}),
            'filemask': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'git_export': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'license': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '150', 'blank': 'True'}),
            'license_url': ('django.db.models.fields.URLField', [], {'default': "''", 'max_length': '200', 'blank': 'True'}),
            'locked': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'merge_style': ('django.db.models.fields.CharField', [], {'default': "'merge'", 'max_length': '10'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'new_base': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            'new_lang': ('django.db.models.fields.CharField', [], {'default': "'contact'", 'max_length': '10'}),
            'pre_commit_script': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '200', 'blank': 'True'}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'push': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'}),
            'repo': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'report_source_bugs': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'repoweb': ('django.db.models.fields.URLField', [], {'max_length': '200', 'blank': 'True'}),
            'save_history': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'suggestion_autoaccept': ('django.db.models.fields.PositiveSmallIntegerField', [], {'default': '0'}),
            'suggestion_voting': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'template': ('django.db.models.fields.CharField', [], {'max_length': '200', 'blank': 'True'})
        },
        'trans.suggestion': {
            'Meta': {'object_name': 'Suggestion'},
            'contentsum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['lang.Language']"}),
            'project': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Project']"}),
            'target': ('django.db.models.fields.TextField', [], {}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['auth.User']", 'null': 'True', 'blank': 'True'}),
            'votes': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'user_votes'", 'symmetrical': 'False', 'through': "orm['trans.Vote']", 'to': u"orm['auth.User']"})
        },
        'trans.translation': {
            'Meta': {'ordering': "['language__name']", 'object_name': 'Translation'},
            'commit_message': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'enabled': ('django.db.models.fields.BooleanField', [], {'default': 'True', 'db_index': 'True'}),
            'failing_checks': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'failing_checks_words': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'filename': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'fuzzy': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'fuzzy_words': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'have_suggestion': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'language': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['lang.Language']"}),
            'language_code': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '20'}),
            'lock_time': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'lock_user': ('django.db.models.fields.related.ForeignKey', [], {'default': 'None', 'to': u"orm['auth.User']", 'null': 'True', 'blank': 'True'}),
            'revision': ('django.db.models.fields.CharField', [], {'default': "''", 'max_length': '100', 'blank': 'True'}),
            'subproject': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.SubProject']"}),
            'total': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'total_words': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'translated': ('django.db.models.fields.IntegerField', [], {'default': '0', 'db_index': 'True'}),
            'translated_words': ('django.db.models.fields.IntegerField', [], {'default': '0'})
        },
        'trans.unit': {
            'Meta': {'ordering': "['priority', 'position']", 'object_name': 'Unit'},
            'checksum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'comment': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'contentsum': ('django.db.models.fields.CharField', [], {'max_length': '40', 'db_index': 'True'}),
            'context': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'flags': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'fuzzy': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'has_comment': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'has_failing_check': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'has_suggestion': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'location': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'num_words': ('django.db.models.fields.IntegerField', [], {'default': '0'}),
            'position': ('django.db.models.fields.IntegerField', [], {'db_index': 'True'}),
            'previous_source': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'priority': ('django.db.models.fields.IntegerField', [], {'default': '100', 'db_index': 'True'}),
            'source': ('django.db.models.fields.TextField', [], {}),
            'target': ('django.db.models.fields.TextField', [], {'default': "''", 'blank': 'True'}),
            'translated': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'translation': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Translation']"})
        },
        'trans.vote': {
            'Meta': {'unique_together': "(('suggestion', 'user'),)", 'object_name': 'Vote'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'positive': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'suggestion': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['trans.Suggestion']"}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['auth.User']"})
        },
        'trans.whiteboardmessage': {
            'Meta': {'object_name': 'WhiteboardMessage'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'message': ('django.db.models.fields.TextField', [], {'blank': 'True'})
        }
    }

    complete_apps = ['trans']
