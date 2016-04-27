# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
import weblate.trans.mixins
import weblate.trans.validators
import weblate.trans.models.subproject
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('lang', '0001_initial'),
        ('auth', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Advertisement',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('placement', models.IntegerField(verbose_name='Placement', choices=[(1, 'Mail footer (text)'), (2, 'Mail footer (HTML)')])),
                ('date_start', models.DateField(verbose_name='Start date')),
                ('date_end', models.DateField(verbose_name='End date')),
                ('text', models.TextField(help_text='Depending on placement, HTML can be allowed.', verbose_name='Text')),
                ('note', models.TextField(help_text='Free form note for your notes, not used within Weblate.', verbose_name='Note', blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Change',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('action', models.IntegerField(default=2, choices=[(0, 'Resource update'), (1, 'Translation completed'), (2, 'Translation changed'), (5, 'New translation'), (3, 'Comment added'), (4, 'Suggestion added'), (6, 'Automatic translation'), (7, 'Suggestion accepted'), (8, 'Translation reverted'), (9, 'Translation uploaded'), (10, 'Glossary added'), (11, 'Glossary updated'), (12, 'Glossary uploaded'), (13, 'New source string')])),
                ('target', models.TextField(default=b'', blank=True)),
                ('author', models.ForeignKey(related_name=b'author_set', to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Check',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('contentsum', models.CharField(max_length=40, db_index=True)),
                ('check', models.CharField(max_length=20, choices=[(b'end_space', 'Trailing space'), (b'inconsistent', 'Inconsistent'), (b'begin_newline', 'Starting newline'), (b'zero-width-space', 'Zero-width space'), (b'escaped_newline', 'Mismatched \\n'), (b'same', 'Not translated'), (b'end_question', 'Trailing question'), (b'end_ellipsis', 'Trailing ellipsis'), (b'ellipsis', 'Ellipsis'), (b'python_brace_format', 'Python brace format'), (b'end_newline', 'Trailing newline'), (b'c_format', 'C format'), (b'optional_plural', 'Optional plural'), (b'end_exclamation', 'Trailing exclamation'), (b'end_colon', 'Trailing colon'), (b'xml-tags', 'XML tags mismatch'), (b'python_format', 'Python format'), (b'plurals', 'Missing plurals'), (b'begin_space', 'Starting spaces'), (b'bbcode', 'Mismatched BBcode'), (b'multiple_failures', 'Multiple failing checks'), (b'php_format', 'PHP format'), (b'end_stop', 'Trailing stop')])),
                ('ignore', models.BooleanField(default=False, db_index=True)),
                ('language', models.ForeignKey(blank=True, to='lang.Language', null=True)),
            ],
            options={
                'permissions': (('ignore_check', 'Can ignore check results'),),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('contentsum', models.CharField(max_length=40, db_index=True)),
                ('comment', models.TextField()),
                ('timestamp', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('language', models.ForeignKey(blank=True, to='lang.Language', null=True)),
            ],
            options={
                'ordering': ['timestamp'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Dictionary',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('source', models.CharField(max_length=100, db_index=True)),
                ('target', models.CharField(max_length=100)),
                ('language', models.ForeignKey(to='lang.Language')),
            ],
            options={
                'ordering': ['source'],
                'permissions': (('upload_dictionary', 'Can import dictionary'),),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='IndexUpdate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('source', models.BooleanField(default=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(help_text='Name to display', unique=True, max_length=100, verbose_name='Project name')),
                ('slug', models.SlugField(help_text='Name used in URLs and file names.', unique=True, verbose_name='URL slug')),
                ('web', models.URLField(help_text='Main website of translated project.', verbose_name='Project website')),
                ('mail', models.EmailField(help_text='Mailing list for translators.', max_length=75, verbose_name='Mailing list', blank=True)),
                ('instructions', models.URLField(help_text='URL with instructions for translators.', verbose_name='Translation instructions', blank=True)),
                ('license', models.CharField(help_text='Optional short summary of license used for translations.', max_length=150, verbose_name='Translation license', blank=True)),
                ('license_url', models.URLField(help_text='Optional URL with license details.', verbose_name='License URL', blank=True)),
                ('new_lang', models.CharField(default=b'contact', help_text='How to handle requests for creating new languages.', max_length=10, verbose_name='New language', choices=[(b'contact', 'Use contact form'), (b'url', 'Point to translation instructions URL'), (b'add', 'Automatically add language file'), (b'none', 'No adding of language')])),
                ('merge_style', models.CharField(default=b'merge', help_text='Define whether Weblate should merge upstream repository or rebase changes onto it.', max_length=10, verbose_name='Merge style', choices=[(b'merge', 'Merge'), (b'rebase', 'Rebase')])),
                ('commit_message', models.TextField(default=b'Translated using Weblate (%(language_name)s)\n\nCurrently translated at %(translated_percent)s%% (%(translated)s of %(total)s strings)', help_text='You can use format strings for various information, please check documentation for more details.', verbose_name='Commit message', validators=[weblate.trans.validators.validate_commit_message])),
                ('committer_name', models.CharField(default=b'Weblate', max_length=200, verbose_name='Committer name')),
                ('committer_email', models.EmailField(default=b'noreply@weblate.org', max_length=75, verbose_name='Committer email')),
                ('push_on_commit', models.BooleanField(default=False, help_text='Whether the repository should be pushed upstream on every commit.', verbose_name='Push on commit')),
                ('set_translation_team', models.BooleanField(default=True, help_text='Whether the Translation-Team in file headers should be updated by Weblate.', verbose_name='Set Translation-Team header')),
                ('enable_acl', models.BooleanField(default=False, help_text='Whether to enable ACL for this project, please check documentation before enabling this.', verbose_name='Enable ACL')),
            ],
            options={
                'ordering': ['name'],
            },
            bases=(models.Model, weblate.trans.mixins.PercentMixin, weblate.trans.mixins.URLMixin, weblate.trans.mixins.PathMixin),
        ),
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('checksum', models.CharField(max_length=40)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('priority', models.IntegerField(default=100, choices=[(60, 'Very high'), (80, 'High'), (100, 'Medium'), (120, 'Low'), (140, 'Very low')])),
            ],
            options={
                'permissions': (('edit_priority', 'Can edit priority'),),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SubProject',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(help_text='Name to display', max_length=100, verbose_name='Subproject name')),
                ('slug', models.SlugField(help_text='Name used in URLs and file names.', verbose_name='URL slug')),
                ('repo', models.CharField(help_text='URL of Git repository, use weblate://project/subproject for sharing with other subproject.', max_length=200, verbose_name='Git repository')),
                ('push', models.CharField(help_text='URL of push Git repository, pushing is disabled if empty.', max_length=200, verbose_name='Git push URL', blank=True)),
                ('repoweb', models.URLField(blank=True, help_text='Link to repository browser, use %(branch)s for branch, %(file)s and %(line)s as filename and line placeholders.', verbose_name='Repository browser', validators=[weblate.trans.validators.validate_repoweb])),
                ('git_export', models.CharField(help_text='URL of Git repository where users can fetch changes from Weblate', max_length=200, verbose_name='Exported Git URL', blank=True)),
                ('report_source_bugs', models.EmailField(help_text='Email address where errors in source string will be reported, keep empty for no emails.', max_length=75, verbose_name='Source string bug report address', blank=True)),
                ('branch', models.CharField(default=b'master', help_text='Git branch to translate', max_length=50, verbose_name='Git branch')),
                ('filemask', models.CharField(help_text='Path of files to translate, use * instead of language code, for example: po/*.po or locale/*/LC_MESSAGES/django.po.', max_length=200, verbose_name='File mask', validators=[weblate.trans.validators.validate_filemask])),
                ('template', models.CharField(help_text='Filename of translations base file, which contains all strings and their source; this is recommended to use for monolingual translation formats.', max_length=200, verbose_name='Monolingual base language file', blank=True)),
                ('new_base', models.CharField(help_text='Filename of file which is used for creating new translations. For Gettext choose .pot file.', max_length=200, verbose_name='Base file for new translations', blank=True)),
                ('file_format', models.CharField(default=b'auto', help_text='Automatic detection might fail for some formats and is slightly slower.', max_length=50, verbose_name='File format', choices=[(b'aresource', 'Android String Resource'), (b'auto', 'Automatic detection'), (b'json', 'JSON file'), (b'php', 'PHP strings'), (b'po', 'Gettext PO file'), (b'po-mono', 'Gettext PO file (monolingual)'), (b'properties', 'Java Properties'), (b'properties-utf8', 'Java Properties (UTF-8)'), (b'strings', 'OS X Strings'), (b'strings-utf8', 'OS X Strings (UTF-8)'), (b'ts', 'Qt Linguist Translation File'), (b'xliff', 'XLIFF Translation File')])),
                ('extra_commit_file', models.CharField(default=b'', validators=[weblate.trans.validators.validate_extra_file], max_length=200, blank=True, help_text='Additional file to include in commits; please check documentation for more details.', verbose_name='Additional commit file')),
                ('pre_commit_script', models.CharField(default=b'', choices=[(b'', b'')], max_length=200, blank=True, help_text='Script to be executed before committing translation, please check documentation for more details.', verbose_name='Pre-commit script')),
                ('locked', models.BooleanField(default=False, help_text='Whether subproject is locked for translation updates.', verbose_name='Locked')),
                ('allow_translation_propagation', models.BooleanField(default=True, help_text='Whether translation updates in other subproject will cause automatic translation in this project', verbose_name='Allow translation propagation')),
                ('save_history', models.BooleanField(default=True, help_text='Whether Weblate should keep history of translations', verbose_name='Save translation history')),
                ('enable_suggestions', models.BooleanField(default=True, help_text='Whether to allow translation suggestions at all.', verbose_name='Enable suggestions')),
                ('suggestion_voting', models.BooleanField(default=False, help_text='Whether users can vote for suggestions.', verbose_name='Suggestion voting')),
                ('suggestion_autoaccept', models.PositiveSmallIntegerField(default=0, help_text='Automatically accept suggestions with this number of votes, use 0 to disable.', verbose_name='Autoaccept suggestions', validators=[weblate.trans.validators.validate_autoaccept])),
                ('check_flags', models.TextField(default=b'', help_text='Additional comma-separated flags to influence quality checks, check documentation for possible values.', blank=True, verbose_name='Quality checks flags', validators=[weblate.trans.validators.validate_check_flags])),
                ('project', models.ForeignKey(verbose_name='Project', to='trans.Project')),
            ],
            options={
                'ordering': ['project__name', 'name'],
                'permissions': (('lock_subproject', 'Can lock translation for translating'), ('can_see_git_repository', 'Can see git repository URL')),
            },
            bases=(models.Model, weblate.trans.mixins.PercentMixin, weblate.trans.mixins.URLMixin, weblate.trans.mixins.PathMixin),
        ),
        migrations.CreateModel(
            name='Suggestion',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('contentsum', models.CharField(max_length=40, db_index=True)),
                ('target', models.TextField()),
                ('language', models.ForeignKey(to='lang.Language')),
                ('project', models.ForeignKey(to='trans.Project')),
                ('user', models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'permissions': (('accept_suggestion', 'Can accept suggestion'), ('override_suggestion', 'Can override suggestion state'), ('vote_suggestion', 'Can vote for suggestion')),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Translation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('revision', models.CharField(default=b'', max_length=100, blank=True)),
                ('filename', models.CharField(max_length=200)),
                ('translated', models.IntegerField(default=0, db_index=True)),
                ('fuzzy', models.IntegerField(default=0, db_index=True)),
                ('total', models.IntegerField(default=0, db_index=True)),
                ('translated_words', models.IntegerField(default=0)),
                ('fuzzy_words', models.IntegerField(default=0)),
                ('failing_checks_words', models.IntegerField(default=0)),
                ('total_words', models.IntegerField(default=0)),
                ('failing_checks', models.IntegerField(default=0, db_index=True)),
                ('have_suggestion', models.IntegerField(default=0, db_index=True)),
                ('enabled', models.BooleanField(default=True, db_index=True)),
                ('language_code', models.CharField(default=b'', max_length=20)),
                ('lock_time', models.DateTimeField(default=django.utils.timezone.now)),
                ('commit_message', models.TextField(default=b'', blank=True)),
                ('language', models.ForeignKey(to='lang.Language')),
                ('lock_user', models.ForeignKey(default=None, blank=True, to=settings.AUTH_USER_MODEL, null=True)),
                ('subproject', models.ForeignKey(to='trans.SubProject')),
            ],
            options={
                'ordering': ['language__name'],
                'permissions': (('upload_translation', 'Can upload translation'), ('overwrite_translation', 'Can overwrite with translation upload'), ('author_translation', 'Can define author of translation upload'), ('commit_translation', 'Can force commiting of translation'), ('update_translation', 'Can update translation from'), ('push_translation', 'Can push translations to remote'), ('reset_translation', 'Can reset translations to match remote'), ('automatic_translation', 'Can do automatic translation'), ('lock_translation', 'Can lock whole translation project'), ('use_mt', 'Can use machine translation')),
            },
            bases=(models.Model, weblate.trans.mixins.URLMixin, weblate.trans.mixins.PercentMixin),
        ),
        migrations.CreateModel(
            name='Unit',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('checksum', models.CharField(max_length=40, db_index=True)),
                ('contentsum', models.CharField(max_length=40, db_index=True)),
                ('location', models.TextField(default=b'', blank=True)),
                ('context', models.TextField(default=b'', blank=True)),
                ('comment', models.TextField(default=b'', blank=True)),
                ('flags', models.TextField(default=b'', blank=True)),
                ('source', models.TextField()),
                ('previous_source', models.TextField(default=b'', blank=True)),
                ('target', models.TextField(default=b'', blank=True)),
                ('fuzzy', models.BooleanField(default=False, db_index=True)),
                ('translated', models.BooleanField(default=False, db_index=True)),
                ('position', models.IntegerField(db_index=True)),
                ('has_suggestion', models.BooleanField(default=False, db_index=True)),
                ('has_comment', models.BooleanField(default=False, db_index=True)),
                ('has_failing_check', models.BooleanField(default=False, db_index=True)),
                ('num_words', models.IntegerField(default=0)),
                ('priority', models.IntegerField(default=100, db_index=True)),
                ('translation', models.ForeignKey(to='trans.Translation')),
            ],
            options={
                'ordering': ['priority', 'position'],
                'permissions': (('save_translation', 'Can save translation'),),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Vote',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('positive', models.BooleanField(default=True)),
                ('suggestion', models.ForeignKey(to='trans.Suggestion')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WhiteboardMessage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('message', models.TextField(blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='vote',
            unique_together=set([('suggestion', 'user')]),
        ),
        migrations.AddField(
            model_name='suggestion',
            name='votes',
            field=models.ManyToManyField(related_name=b'user_votes', through='trans.Vote', to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='subproject',
            unique_together=set([('project', 'name'), ('project', 'slug')]),
        ),
        migrations.AddField(
            model_name='source',
            name='subproject',
            field=models.ForeignKey(to='trans.SubProject'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='source',
            unique_together=set([('checksum', 'subproject')]),
        ),
        migrations.AddField(
            model_name='indexupdate',
            name='unit',
            field=models.ForeignKey(to='trans.Unit', unique=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='dictionary',
            name='project',
            field=models.ForeignKey(to='trans.Project'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='comment',
            name='project',
            field=models.ForeignKey(to='trans.Project'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='comment',
            name='user',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='check',
            name='project',
            field=models.ForeignKey(to='trans.Project'),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='check',
            unique_together=set([('contentsum', 'project', 'language', 'check')]),
        ),
        migrations.AddField(
            model_name='change',
            name='dictionary',
            field=models.ForeignKey(to='trans.Dictionary', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='change',
            name='translation',
            field=models.ForeignKey(to='trans.Translation', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='change',
            name='unit',
            field=models.ForeignKey(to='trans.Unit', null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='change',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='advertisement',
            index_together=set([('placement', 'date_start', 'date_end')]),
        ),
    ]
