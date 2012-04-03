from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.conf import settings
from lang.models import Language
from django.db.models import Sum
from django.utils.translation import ugettext_lazy, ugettext as _
from django.utils.safestring import mark_safe
from django.core.mail import mail_admins
from django.core.exceptions import ValidationError
from django.contrib import messages
from glob import glob
import os
import time
import random
import os.path
import logging
import git
import traceback
from translate.storage import factory
from translate.storage import poheader
from datetime import datetime

import trans
import trans.checks
from trans.managers import TranslationManager, UnitManager, DictionaryManager
from util import is_plural, split_plural, join_plural

logger = logging.getLogger('weblate')

def validate_repoweb(val):
    try:
        test = val % {'file': 'file.po', 'line': '9'}
    except Exception, e:
        raise ValidationError(_('Bad format string (%s)') % str(e))

class Project(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    web = models.URLField()
    mail = models.EmailField(blank = True)
    instructions = models.URLField(blank = True)

    class Meta:
        ordering = ['name']

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_commit_url(self):
        return ('trans.views.commit_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_update_url(self):
        return ('trans.views.update_project', (), {
            'project': self.slug
        })

    def get_path(self):
        return os.path.join(settings.GIT_ROOT, self.slug)

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Create filesystem directory for storing data
        p = self.get_path()
        if not os.path.exists(p):
            os.makedirs(p)

        super(Project, self).save(*args, **kwargs)

    def get_translated_percent(self):
        translations = Translation.objects.filter(subproject__project = self).aggregate(Sum('translated'), Sum('total'))
        if translations['total__sum'] == 0:
            return 0
        return round(translations['translated__sum'] * 100.0 / translations['total__sum'], 1)

    def git_needs_commit(self):
        '''
        Checks whether there are some not commited changes.
        '''
        for s in self.subproject_set.all():
            if s.git_needs_commit():
                return True
        return False

    def git_needs_pull(self, gitrepo = None):
        for s in self.subproject_set.all():
            if s.git_needs_pull():
                return True
        return False

    def git_needs_push(self, gitrepo = None):
        for s in self.subproject_set.all():
            if s.git_needs_push():
                return True
        return False

    def commit_pending(self):
        '''
        Commits any pending changes.
        '''
        for s in self.subproject_set.all():
            s.commit_pending()

    def do_update(self, request = None):
        '''
        Updates all git repos.
        '''
        ret = True
        for s in self.subproject_set.all():
            ret &= s.do_update(request)
        return ret

    def do_push(self, request = None):
        '''
        Pushes all git repos.
        '''
        ret = True
        for s in self.subproject_set.all():
            ret &= s.do_push(request)
        return ret

class SubProject(models.Model):
    name = models.CharField(max_length = 100, help_text = _('Name to display'))
    slug = models.SlugField(db_index = True, help_text = _('Name used in URLs'))
    project = models.ForeignKey(Project)
    repo = models.CharField(max_length = 200, help_text = _('URL of Git repository'))
    push = models.CharField(max_length = 200, help_text = _('URL of push Git repository'), blank = True)
    repoweb = models.URLField(
        help_text = _('Link to repository browser, use %(branch)s for branch, %(file)s and %(line)s as filename and line placeholders'),
        validators = [validate_repoweb])
    branch = models.CharField(max_length = 50, help_text = _('Git branch to translate'))
    filemask = models.CharField(max_length = 200, help_text = _('Mask of files to translate, use * instead of language code'))

    class Meta:
        ordering = ['name']

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_commit_url(self):
        return ('trans.views.commit_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_update_url(self):
        return ('trans.views.update_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    def __unicode__(self):
        return '%s/%s' % (self.project.__unicode__(), self.name)

    def get_path(self):
        return os.path.join(self.project.get_path(), self.slug)

    def get_repo(self):
        '''
        Gets Git repository object.
        '''
        p = self.get_path()
        try:
            return git.Repo(p)
        except:
            return git.Repo.init(p)

    def get_repoweb_link(self, filename, line):
        return self.repoweb % {
            'file': filename,
            'line': line,
            'branch': self.branch
        }

    def configure_repo(self):
        '''
        Ensures repository is correctly configured and points to current remote.
        '''
        # Create/Open repo
        gitrepo = self.get_repo()
        # Get/Create origin remote
        try:
            origin = gitrepo.remotes.origin
        except:
            gitrepo.git.remote('add', 'origin', self.repo)
            origin = gitrepo.remotes.origin
        # Check remote source
        if origin.url != self.repo:
            gitrepo.git.remote('set-url', 'origin', self.repo)
        # Check push url
        try:
            pushurl = origin.pushurl
        except AttributeError:
            pushurl = ''
        if pushurl != self.push:
            gitrepo.git.remote('set-url', 'origin', '--push', self.push)
        # Update
        logger.info('updating repo %s', self.__unicode__())
        try:
            gitrepo.git.remote('update', 'origin')
        except Exception, e:
            logger.error('Failed to update Git repo: %s', str(e))
        del gitrepo


    def configure_branch(self):
        '''
        Ensures local tracking branch exists and is checkouted.
        '''
        gitrepo = self.get_repo()
        try:
            head = gitrepo.heads[self.branch]
        except:
            gitrepo.git.branch('--track', self.branch, 'origin/%s' % self.branch)
            head = gitrepo.heads[self.branch]
        gitrepo.git.checkout(self.branch)
        del gitrepo

    def do_update(self, request = None):
        '''
        Wrapper for doing repository update and pushing them to translations.
        '''
        self.commit_pending()
        ret = self.update_branch(request)
        self.create_translations()
        return ret

    def do_push(self, request = None):
        '''
        Wrapper for pushing changes to remote repo.
        '''
        # Do we have push configured
        if self.push == '':
            messages.error(request, _('Push is disabled for %s.') % self.__unicode__())
            return False

        # First check we're up to date
        if not self.do_update(request):
            return False

        # Do actual push
        gitrepo = self.get_repo()
        try:
            logger.info('pushing to remote repo %s', self.__unicode__())
            gitrepo.git.push('origin', '%s:%s' % (self.branch, self.branch))
        except Exception, e:
            logger.warning('failed push on repo %s', self.__unicode__())
            msg = 'Error:\n%s' % str(e)
            mail_admins(
                'failed push on repo %s' % self.__unicode__(),
                msg
            )
            if request is not None:
                messages.error(request, _('Failed to push to remote branch on %s.') % self.__unicode__())
                return False
        del gitrepo
        return True

    def commit_pending(self):
        '''
        Checks whether there is any translation which needs commit.
        '''
        for translation in self.translation_set.all():
            translation.commit_pending()

    def update_branch(self, request = None):
        '''
        Updates current branch to match remote (if possible).
        '''
        gitrepo = self.get_repo()
        logger.info('pulling from remote repo %s', self.__unicode__())
        gitrepo.remotes.origin.update()
        ret = False
        try:
            gitrepo.git.merge('origin/%s' % self.branch)
            logger.info('merged remote into repo %s', self.__unicode__())
            ret = True
        except Exception, e:
            status = gitrepo.git.status()
            gitrepo.git.merge('--abort')
            logger.warning('failed merge on repo %s', self.__unicode__())
            msg = 'Error:\n%s' % str(e)
            msg += '\n\nStatus:\n' + status
            mail_admins(
                'failed merge on repo %s' % self.__unicode__(),
                msg
            )
            if request is not None:
                messages.error(request, _('Failed to merge remote branch into %s.') % self.__unicode__())

        del gitrepo
        return ret

    def get_translation_blobs(self):
        '''
        Iterator over translations in filesystem.
        '''
        gitrepo = self.get_repo()
        tree = gitrepo.tree()

        # Glob files
        prefix = os.path.join(self.get_path(), '')
        for f in glob(os.path.join(self.get_path(), self.filemask)):
            filename = f.replace(prefix, '')
            yield (
                self.get_lang_code(filename),
                filename,
                tree[filename].hexsha
                )
        del gitrepo

    def create_translations(self, force = False):
        '''
        Loads translations from git.
        '''
        for code, path, blob_hash in self.get_translation_blobs():
            logger.info('checking %s', path)
            Translation.objects.update_from_blob(self, code, path, blob_hash, force)

    def get_lang_code(self, path):
        '''
        Parses language code from path.
        '''
        parts = self.filemask.split('*')
        return path[len(parts[0]):-len(parts[1])]

    def save(self, *args, **kwargs):
        self.configure_repo()
        self.configure_branch()
        self.commit_pending()
        self.update_branch()

        super(SubProject, self).save(*args, **kwargs)

        self.create_translations()

    def get_translated_percent(self):
        translations = self.translation_set.aggregate(Sum('translated'), Sum('total'))
        if translations['total__sum'] == 0:
            return 0
        return round(translations['translated__sum'] * 100.0 / translations['total__sum'], 1)

    def git_needs_commit(self, gitrepo = None):
        '''
        Checks whether there are some not commited changes.
        '''
        if gitrepo is None:
            gitrepo = self.get_repo()
        status = gitrepo.git.status('--porcelain')
        if status == '':
            # No changes to commit
            return False
        return True

    def git_check_merge(self, revision, gitrepo = None):
        if gitrepo is None:
            gitrepo = self.get_repo()
        status = gitrepo.git.log(revision)
        del gitrepo
        if status == '':
            # No changes to merge
            return False
        return True

    def git_needs_pull(self, gitrepo = None):
        return self.git_check_merge('..origin/%s' % self.branch, gitrepo)

    def git_needs_push(self, gitrepo = None):
        return self.git_check_merge('origin/%s..' % self.branch, gitrepo)


class Translation(models.Model):
    subproject = models.ForeignKey(SubProject)
    language = models.ForeignKey(Language)
    revision = models.CharField(max_length = 40, default = '', blank = True)
    filename = models.CharField(max_length = 200)\

    translated = models.IntegerField(default = 0, db_index = True)
    fuzzy = models.IntegerField(default = 0, db_index = True)
    total = models.IntegerField(default = 0, db_index = True)

    objects = TranslationManager()

    class Meta:
        ordering = ['language__name']
        permissions = (
            ('upload_translation', "Can upload translation"),
            ('overwrite_translation', "Can overwrite with translation upload"),
            ('author_translation', "Can define author of translation upload"),
            ('commit_translation', "Can force commiting of translation"),
            ('update_translation', "Can update translation from git"),
            ('automatic_translation', "Can do automatic translation"),
        )

    def get_fuzzy_percent(self):
        if self.total == 0:
            return 0
        return round(self.fuzzy * 100.0 / self.total, 1)

    def get_translated_percent(self):
        if self.total == 0:
            return 0
        return round(self.translated * 100.0 / self.total, 1)

    def get_non_translated(self):
        return self.total - self.translated

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_commit_url(self):
        return ('trans.views.commit_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_update_url(self):
        return ('trans.views.update_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_download_url(self):
        return ('trans.views.download_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_translate_url(self):
        return ('trans.views.translate', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    def __unicode__(self):
        return '%s - %s' % (self.subproject.__unicode__(), _(self.language.name))

    def get_filename(self):
        return os.path.join(self.subproject.get_path(), self.filename)

    def get_store(self):
        return factory.getobject(self.get_filename())

    def check_sync(self):
        '''
        Checks whether database is in sync with git and possibly does update.
        '''
        self.update_from_blob()

    def update_from_blob(self, blob_hash = None, force = False):
        '''
        Updates translation data from blob.
        '''
        if blob_hash is None:
            blob_hash = self.get_git_blob_hash()

        # Check if we're not already up to date
        if self.revision == blob_hash and not force:
            return

        logger.info('processing %s, revision has changed', self.filename)

        oldunits = set(self.unit_set.all().values_list('id', flat = True))

        # Load po file
        store = self.get_store()
        for pos, unit in enumerate(store.units):
            if not unit.istranslatable():
                continue
            newunit = Unit.objects.update_from_unit(self, unit, pos)
            try:
                oldunits.remove(newunit.id)
            except:
                pass

        # Delete not used units
        units_to_delete = Unit.objects.filter(translation = self, id__in = oldunits)
        deleted_checksums = units_to_delete.values_list('checksum', flat = True)
        units_to_delete.delete()

        # Cleanup checks for deleted units
        for checksum in deleted_checksums:
            units = Unit.objects.filter(translation__language = self.language, translation__subproject__project = self.subproject.project, checksum = checksum)
            if units.count() == 0:
                # Last unit referencing to these checks
                Checks.objects.filter(project = self.subproject.project, language = self.language, checksum = checksum).delete()
            else:
                # There are other units as well, but some checks (eg. consistency) needs update now
                for unit in units:
                    unit.check()

        # Update revision and stats
        self.update_stats(blob_hash)

    def get_repo(self):
        return self.subproject.get_repo()

    def do_update(self, request = None):
        return self.subproject.do_update(request)

    def do_push(self, request = None):
        return self.subproject.do_push(request)

    def get_git_blob_hash(self):
        '''
        Returns current Git blob hash for file.
        '''
        gitrepo = self.get_repo()
        tree = gitrepo.tree()
        ret = tree[self.filename].hexsha
        del gitrepo
        return ret

    def update_stats(self, blob_hash = None):
        '''
        Updates translation statistics.
        '''
        if blob_hash is None:
            blob_hash = self.get_git_blob_hash()
        self.total = self.unit_set.count()
        self.fuzzy = self.unit_set.filter(fuzzy = True).count()
        self.translated = self.unit_set.filter(translated = True).count()
        self.revision = blob_hash
        self.save()

    def get_last_author(self):
        try:
            change = Change.objects.filter(unit__translation = self).order_by('-timestamp')[0]
            return self.get_author_name(change.user)
        except IndexError:
            return None

    def commit_pending(self, author = None):
        last = self.get_last_author()
        if author == last or last is None:
            return
        self.git_commit(last, True)

    def get_author_name(self, user):
        full_name = user.get_full_name()
        if full_name == '':
            full_name = user.username
        return '%s <%s>' % (full_name, user.email)

    def __git_commit(self, gitrepo, author):
        '''
        Commits translation to git.
        '''
        gitrepo.git.commit(
            self.filename,
            author = author.encode('utf-8'),
            m = settings.COMMIT_MESSAGE
            )

    def git_needs_commit(self, gitrepo = None):
        '''
        Checks whether there are some not commited changes.
        '''
        if gitrepo is None:
            gitrepo = self.get_repo()
        status = gitrepo.git.status('--porcelain', '--', self.filename)
        if status == '':
            # No changes to commit
            return False
        return True

    def git_needs_pull(self):
        return self.subproject.git_needs_pull()

    def git_needs_push(self):
        return self.subproject.git_needs_push()

    def git_commit(self, author, force_commit = False):
        '''
        Wrapper for commiting translation to git.
        '''
        gitrepo = self.get_repo()
        if not self.git_needs_commit(gitrepo):
            return False
        if not force_commit and settings.LAZY_COMMITS:
            logger.info('Delaying commiting %s in %s as %s', self.filename, self, author)
            return False
        logger.info('Commiting %s in %s as %s', self.filename, self, author)
        try:
            self.__git_commit(gitrepo, author)
        except git.GitCommandError:
            # There might be another attempt on commit in same time
            # so we will sleep a bit an retry
            time.sleep(random.random() * 2)
            self.__git_commit(gitrepo, author)
        del gitrepo
        return True

    def update_unit(self, unit, request):
        '''
        Updates backend file and unit.
        '''
        store = self.get_store()
        src = unit.get_source_plurals()[0]
        need_save = False
        for pounit in store.findunits(src):
            if pounit.getcontext() == unit.context:
                if hasattr(pounit.target, 'strings'):
                    potarget = join_plural(pounit.target.strings)
                else:
                    potarget = pounit.target
                if unit.target != potarget or unit.fuzzy != pounit.isfuzzy():
                    pounit.markfuzzy(unit.fuzzy)
                    if unit.is_plural():
                        pounit.settarget(unit.get_target_plurals())
                    else:
                        pounit.settarget(unit.target)
                    need_save = True
                # We should have only one match
                break
        if need_save:
            author = self.get_author_name(request.user)
            if hasattr(store, 'updateheader'):
                po_revision_date = datetime.now().strftime('%Y-%m-%d %H:%M') + poheader.tzstring()

                store.updateheader(
                    add = True,
                    last_translator = author,
                    plural_forms = self.language.get_plural_form(),
                    language = self.language.code,
                    PO_Revision_Date = po_revision_date,
                    x_generator = 'Weblate %s' % trans.VERSION
                    )
            self.commit_pending(author)
            store.save()
            self.git_commit(author)

        return need_save, pounit

    def get_translation_checks(self):
        '''
        Returns list of failing checks on current translation.
        '''
        result = [('all', _('All strings'))]
        nottranslated = self.unit_set.filter_type('untranslated').count()
        fuzzy = self.unit_set.filter_type('fuzzy').count()
        suggestions = self.unit_set.filter_type('suggestions').count()
        if nottranslated > 0:
            result.append(('untranslated', _('Not translated strings (%d)') % nottranslated))
        if fuzzy > 0:
            result.append(('fuzzy', _('Fuzzy strings (%d)') % fuzzy))
        if suggestions > 0:
            result.append(('suggestions', _('Strings with suggestions (%d)') % suggestions))
        for check in trans.checks.CHECKS:
            cnt = self.unit_set.filter_type(check).count()
            if cnt > 0:
                desc =  trans.checks.CHECKS[check].description + (' (%d)' % cnt)
                result.append((check, desc))
        return result

    def merge_store(self, author, store2, overwrite, mergefuzzy = False):
        '''
        Merges ttkit store into current translation.
        '''
        store1 = self.get_store()
        store1.require_index()

        for unit2 in store2.units:
            if unit2.isheader():
                if isinstance(store1, poheader.poheader):
                    store1.mergeheaders(store2)
                continue
            unit1 = store1.findid(unit2.getid())
            if unit1 is None:
                unit1 = store1.findunit(unit2.source)
            if unit1 is None:
                continue
            else:
                if len(unit2.target.strip()) == 0:
                    continue
                if not mergefuzzy:
                    if unit2.isfuzzy():
                        continue
                if not overwrite and unit1.istranslated():
                    continue
                unit1.merge(unit2, overwrite=True, comments=False)
        self.commit_pending(author)
        store1.save()
        ret = self.git_commit(author, True)
        self.check_sync()
        return ret

    def merge_upload(self, request, fileobj, overwrite, author = None, mergefuzzy = False):
        '''
        Top level handler for file uploads.
        '''
        # Needed to behave like something what translate toolkit expects
        fileobj.mode = "r"
        store2 = factory.getobject(fileobj)
        if author is None:
            author = self.get_author_name(request.user)

        ret = False

        for s in Translation.objects.filter(language = self.language, subproject__project = self.subproject.project):
            ret |= s.merge_store(author, store2, overwrite, mergefuzzy)

        return ret

    def get_failing_checks(self, check = None):
        '''
        Returns number of units with failing checks.

        By default for all checks or check type can be specified.
        '''
        if check is None:
            checks = Check.objects.all()
        else:
            checks = Check.objects.filter(check = check)
        checks = checks.filter(project = self.subproject.project, language = self.language, ignore = False).values_list('checksum', flat = True)
        return self.unit_set.filter(checksum__in = checks, translated = True).count()

class Unit(models.Model):
    translation = models.ForeignKey(Translation)
    checksum = models.CharField(max_length = 40, default = '', blank = True, db_index = True)
    location = models.TextField(default = '', blank = True)
    context = models.TextField(default = '', blank = True)
    comment = models.TextField(default = '', blank = True)
    flags = models.TextField(default = '', blank = True)
    source = models.TextField()
    target = models.TextField(default = '', blank = True)
    fuzzy = models.BooleanField(default = False, db_index = True)
    translated = models.BooleanField(default = False, db_index = True)
    position = models.IntegerField(db_index = True)

    objects = UnitManager()

    class Meta:
        permissions = (
            ('save_translation', "Can save translation"),
        )
        ordering = ['position']

    def __unicode__(self):
        return '%s on %s' % (
            self.checksum,
            self.translation,
        )

    def get_absolute_url(self):
        return '%s?pos=%d&dir=stay' % (self.translation.get_translate_url(), self.position)

    def update_from_unit(self, unit, pos, force):
        location = ', '.join(unit.getlocations())
        if hasattr(unit, 'typecomments'):
            flags = ', '.join(unit.typecomments)
        else:
            flags = ''
        if hasattr(unit.target, 'strings'):
            target = join_plural(unit.target.strings)
        else:
            target = unit.target
        fuzzy = unit.isfuzzy()
        translated = unit.istranslated()
        comment = unit.getnotes()
        # Update checks on fuzzy update or on content change
        same_content = (target == self.target and fuzzy == self.fuzzy)
        if not force and location == self.location and flags == self.flags and same_content and fuzzy == self.fuzzy and translated == self.translated and comment == self.comment and pos == self.position:
            return
        self.position = pos
        self.location = location
        self.flags = flags
        self.target = target
        self.fuzzy = fuzzy
        self.translated = translated
        self.comment = comment
        self.save(force_insert = force, backend = True, same_content = same_content)

    def is_plural(self):
        return is_plural(self.source)

    def get_source_plurals(self):
        return split_plural(self.source)

    def get_target_plurals(self):
        if not self.is_plural():
            return [self.target]
        ret = split_plural(self.target)
        plurals = self.translation.language.nplurals
        if len(ret) == plurals:
            return ret

        while len(ret) < plurals:
            ret.append('')

        while len(ret) > plurals:
            del(ret[-1])

        return ret

    def save_backend(self, request, propagate = True, gen_change = True):
        # Store to backend
        (saved, pounit) = self.translation.update_unit(self, request)
        self.translated = pounit.istranslated()
        if hasattr(pounit, 'typecomments'):
            self.flags = ', '.join(pounit.typecomments)
        else:
            self.flags = ''
        self.save(backend = True)
        old_translated = self.translation.translated
        self.translation.update_stats()
        # Force commiting on completing translation
        if old_translated < self.translation.translated and self.translation.translated == self.translation.total:
            self.translation.commit_pending()
        if gen_change:
            Change.objects.create(unit = self, user = request.user)
        # Propagate to other projects
        if propagate:
            allunits = Unit.objects.same(self).exclude(id = self.id)
            for unit in allunits:
                unit.target = self.target
                unit.fuzzy = self.fuzzy
                unit.save_backend(request, False)

    def save(self, *args, **kwargs):
        '''
        Wrapper around save to warn when save did not come from
        git backend (eg. commit or by parsing file).
        '''
        # Warn if request is not coming from backend
        if not 'backend' in kwargs:
            logger.error('Unit.save called without backend sync: %s', ''.join(traceback.format_stack()))
        else:
            del kwargs['backend']

        # Pop parameter indicating that we don't have to process content
        same_content = kwargs.pop('same_content', False)

        # Actually save the unit
        super(Unit, self).save(*args, **kwargs)

        # Update checks and fulltext index if content has changed
        if not same_content:
            self.check()
            Unit.objects.add_to_index(self)

    def get_location_links(self):
        '''
        Generates links to source files where translation was used.
        '''
        ret = []
        if len(self.location) == 0:
            return ''
        for location in self.location.split(','):
            location = location.strip()
            filename, line = location.split(':')
            link = self.translation.subproject.get_repoweb_link(filename, line)
            ret.append('<a href="%s">%s</a>' % (link, location))
        return mark_safe('\n'.join(ret))

    def suggestions(self):
        return Suggestion.objects.filter(
            checksum = self.checksum,
            project = self.translation.subproject.project,
            language = self.translation.language
        )

    def checks(self):
        return Check.objects.filter(
            checksum = self.checksum,
            project = self.translation.subproject.project,
            language = self.translation.language
        )

    def active_checks(self):
        return Check.objects.filter(
            checksum = self.checksum,
            project = self.translation.subproject.project,
            language = self.translation.language,
            ignore = False
        )

    def check(self):
        if self.fuzzy:
            self.checks().delete()
            return
        src = self.get_source_plurals()
        tgt = self.get_target_plurals()
        failing = []
        for check in trans.checks.CHECKS:
            if trans.checks.CHECKS[check].check(src, tgt, self.flags, self.translation.language, self):
                failing.append(check)

        for check in self.checks():
            if check.check in failing:
                failing.remove(check.check)
                continue
            check.delete()

        for check in failing:
            Check.objects.create(
                checksum = self.checksum,
                project = self.translation.subproject.project,
                language = self.translation.language,
                ignore = False,
                check = check
            )

    def nearby(self):
        '''
        Returns list of nearby messages based on location.
        '''
        return Unit.objects.filter(
            translation = self.translation,
            position__gte = self.position - settings.NEARBY_MESSAGES,
            position__lte = self.position + settings.NEARBY_MESSAGES,
        )

class Suggestion(models.Model):
    checksum = models.CharField(max_length = 40, default = '', blank = True, db_index = True)
    target = models.TextField()
    user = models.ForeignKey(User, null = True, blank = True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)

    class Meta:
        permissions = (
            ('accept_suggestion', "Can accept suggestion"),
        )

    def accept(self, request):
        allunits = Unit.objects.filter(
            checksum = self.checksum,
            translation__subproject__project = self.project,
            translation__language = self.language
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = False
            unit.save_backend(request, False)

CHECK_CHOICES = [(x, trans.checks.CHECKS[x].name) for x in trans.checks.CHECKS]

class Check(models.Model):
    checksum = models.CharField(max_length = 40, default = '', blank = True, db_index = True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)
    check = models.CharField(max_length = 20, choices = CHECK_CHOICES)
    ignore = models.BooleanField(db_index = True)

    class Meta:
        permissions = (
            ('ignore_check', "Can ignore check results"),
        )

    def __unicode__(self):
        return '%s/%s: %s' % (
            self.project,
            self.language,
            self.check,
        )

    def get_description(self):
        return trans.checks.CHECKS[self.check].description

    def get_doc_url(self):
        return 'http://weblate.readthedocs.org/en/weblate-%s/usage.html#check-%s' % (
            trans.VERSION,
            self.check,
        )

class Dictionary(models.Model):
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)
    source = models.CharField(max_length = 200, db_index = True)
    target = models.CharField(max_length = 200)

    objects = DictionaryManager()

    class Meta:
        ordering = ['source']
        permissions = (
            ('upload_dictionary', "Can import dictionary"),
        )

    def __unicode__(self):
        return '%s/%s: %s -> %s' % (
            self.project,
            self.language,
            self.source,
            self.target
        )

class Change(models.Model):
    unit = models.ForeignKey(Unit)
    user = models.ForeignKey(User)
    timestamp = models.DateTimeField(auto_now_add = True, db_index = True)

    class Meta:
        ordering = ['-timestamp']

    def __unicode__(self):
        return '%s on %s by %s' % (
            self.unit,
            self.timestamp,
            self.user,
        )
