from django.db import models
from django.db.models import Q
from django.conf import settings
from lang.models import Language
from django.utils.translation import ugettext_lazy, ugettext as _
from glob import glob
import os
import os.path
import logging
import git
import traceback
from translate.storage import factory

from trans.managers import TranslationManager, UnitManager
from util import is_plural, split_plural, join_plural

logger = logging.getLogger('weblate')

class Project(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    web = models.URLField()
    mail = models.EmailField()
    instructions = models.URLField()

    class Meta:
        ordering = ['name']

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_project', (), {
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

class SubProject(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    project = models.ForeignKey(Project)
    repo = models.CharField(max_length = 200)
    branch = models.CharField(max_length = 50)
    filemask = models.CharField(max_length = 200)
    style_choices = (('po', 'GNU Gettext'), ('ts', 'Qt TS'))
    style = models.CharField(max_length = 10, choices = style_choices)

    class Meta:
        ordering = ['name']

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_subproject', (), {
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

    def configure_repo(self):
        '''
        Ensures repository is correctly configured and points to current remote.
        '''
        # Create/Open repo
        repo = self.get_repo()
        # Get/Create origin remote
        try:
            origin = repo.remotes.origin
        except:
            repo.git.remote('add', 'origin', self.repo)
            origin = repo.remotes.origin
        # Check remote source
        if origin.url != self.repo:
            repo.git.remote('set-url', 'origin', self.repo)
        # Update
        logger.info('updating repo %s', self.__unicode__())
        repo.git.remote('update', 'origin')

    def configure_branch(self):
        '''
        Ensures local tracking branch exists and is checkouted.
        '''
        repo = self.get_repo()
        try:
            head = repo.heads[self.branch]
        except:
            repo.git.branch('--track', self.branch, 'origin/%s' % self.branch)
            head = repo.heads[self.branch]
        repo.git.checkout(self.branch)

    def update_branch(self):
        '''
        Updates current branch to match remote (if possible).
        '''
        repo = self.get_repo()
        repo.remotes.origin.pull()
        try:
            repo.git.merge('origin/%s' % self.branch)
        except:
            repo.git.merge('--abort')
            logger.warning('failed merge on repo %s', self.__unicode__())

    def get_translation_blobs(self):
        '''
        Scans directory for translation blobs and returns them as list.
        '''
        repo = self.get_repo()
        tree = repo.tree()

        # Glob files
        files = glob(os.path.join(self.get_path(), self.filemask))
        prefix = os.path.join(self.get_path(), '')
        files = [f.replace(prefix, '') for f in files]

        # Get blobs for files
        return [(self.get_lang_code(f), f, tree[f]) for f in files]

    def create_translations(self, force = False):
        '''
        Loads translations from git.
        '''
        blobs = self.get_translation_blobs()
        for code, path, blob in blobs:
            logger.info('processing %s', path)
            Translation.objects.update_from_blob(self, code, path, blob, force)

    def get_lang_code(self, path):
        '''
        Parses language code from path.
        '''
        parts = self.filemask.split('*')
        return path[len(parts[0]):-len(parts[1])]

    def save(self, *args, **kwargs):
        self.configure_repo()
        self.configure_branch()
        self.update_branch()
        self.create_translations()

        super(SubProject, self).save(*args, **kwargs)

class Translation(models.Model):
    subproject = models.ForeignKey(SubProject)
    language = models.ForeignKey(Language)
    translated = models.FloatField(default = 0, db_index = True)
    fuzzy = models.FloatField(default = 0, db_index = True)
    revision = models.CharField(max_length = 40, default = '', blank = True)
    filename = models.CharField(max_length = 200)

    objects = TranslationManager()

    class Meta:
        ordering = ['language__name']

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_translation', (), {
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
        return '%s %s' % (self.language.name, self.subproject.__unicode__())

    def get_store(self):
        return factory.getobject(os.path.join(self.subproject.get_path(), self.filename))

    def update_from_blob(self, blob, force = False):
        '''
        Updates translation data from blob.
        '''
        # Check if we're not already up to date
        if self.revision == blob.hexsha and not force:
            return

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
        Unit.objects.filter(translation = self, id__in = oldunits).delete()

        # Update revision and stats
        total = self.unit_set.count()
        fuzzy = self.unit_set.filter(fuzzy = True).count()
        translated = self.unit_set.filter(translated = True).count()
        self.fuzzy = round(fuzzy * 100.0 / total, 1)
        self.translated = round(translated * 100.0 / total, 1)
        self.revision = blob.hexsha
        self.save()

    def git_commit(self, author):
        '''
        Commits translation to git.
        '''
        repo = self.subproject.get_repo()
        logger.info('Commiting %s as %s', self.filename, author)
        repo.git.commit(
            self.filename,
            author = author,
            m = 'Translated using Weblate'
            )

    def update_unit(self, unit, request):
        '''
        Updates backend file and unit.
        '''
        store = self.get_store()
        src = unit.get_source_plurals()[0]
        pounits = store.findunits(src)
        need_save = False
        for pounit in pounits:
            if pounit.getcontext() == unit.context:
                if unit.target != join_plural(pounit.target.strings) or unit.fuzzy != pounit.isfuzzy():
                    pounit.markfuzzy(unit.fuzzy)
                    if unit.is_plural():
                        pounit.settarget(unit.get_target_plurals())
                    else:
                        pounit.settarget(unit.target)
                    need_save = True
                # We should have only one match
                break
        if need_save:
            author = '%s <%s>' % (request.user.get_full_name(), request.user.email)
            store.updateheader(add = True, last_translator = author)
            store.save()
            self.git_commit(author)

        return need_save, pounit

    def get_checks(self):
        '''
        Returns list of failing checks on current translation.
        '''
        result = []
        nottranslated = self.unit_set.filter_type('untranslated').count()
        fuzzy = self.unit_set.filter_type('fuzzy').count()
        if nottranslated > 0:
            result.append(('untranslated', _('Not translated strings (%d)') % nottranslated))
        if fuzzy > 0:
            result.append(('fuzzy', _('Fuzzy strings (%d)') % fuzzy))
        return result


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
        ordering = ['position']

    def update_from_unit(self, unit, pos, force):
        location = ', '.join(unit.getlocations())
        flags = ', '.join(unit.typecomments)
        target = join_plural(unit.target.strings)
        fuzzy = unit.isfuzzy()
        translated = unit.istranslated()
        comment = unit.getnotes()
        if not force and location == self.location and flags == self.flags and target == self.target and fuzzy == self.fuzzy and translated == self.translated and comment == self.comment and pos == self.position:
            return
        self.position = pos
        self.location = location
        self.flags = flags
        self.target = target
        self.fuzzy = fuzzy
        self.translated = translated
        self.comment = comment
        self.save(force_insert = force, backend = True)

    def is_plural(self):
        return is_plural(self.source)

    def get_source_plurals(self):
        return split_plural(self.source)

    def get_target_plurals(self):
        ret = split_plural(self.target)
        plurals = self.translation.language.nplurals
        if len(ret) == plurals:
            return ret

        while len(ret) < plurals:
            ret.append('')

        while len(ret) > plurals:
            del(ret[-1])

        return ret

    def save_backend(self, request, propagate = True):
        # Store to backend
        (saved, pounit) = self.translation.update_unit(self, request)
        self.translated = pounit.istranslated()
        self.save(backend = True)
        # Propagate to other projects
        if propagate:
            allunits = Unit.objects.filter(
                checksum = self.checksum,
                translation__subproject__project = self.translation.subproject.project,
                translation__language = self.translation.language
            ).exclude(id = self.id)
            for unit in allunits:
                unit.target = self.target
                unit.save_backend(request, False)

    def save(self, *args, **kwargs):
        if not 'backend' in kwargs:
            logger.error('Unit.save called without backend sync: %s', ''.join(traceback.format_stack()))
        else:
            del kwargs['backend']
        super(Unit, self).save(*args, **kwargs)
