from django.db import models
from django.conf import settings
from lang.models import Language
import os
import os.path
import git

PLURAL_SEPARATOR = '\x00\x00'

class Project(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    web = models.URLField()
    mail = models.EmailField()
    instructions = models.URLField()

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_project', (), {'project': self.slug})

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

    @models.permalink
    def get_absolute_url(self):
         return ('trans.views.show_subproject', (), {'project': self.project.slug, 'subproject': self.slug})

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

    def save(self, *args, **kwargs):
        self.configure_repo()
        self.configure_branch()
        self.update_branch()

        super(SubProject, self).save(*args, **kwargs)

class Translation(models.Model):
    subproject = models.ForeignKey(SubProject)
    language = models.ForeignKey(Language)
    translated = models.FloatField()
    fuzzy = models.FloatField()
    revision = models.CharField(max_length = 40)
    filename = models.CharField(max_length = 200)

    @models.permalink
    def get_absolute_url(self):
         return ('trans.views.show_translation', (), {'project': self.subproject.slug, 'subproject': self.subproject.slug, 'lang': self.language.code})

    def __unicode__(self):
        return '%s@%s' % (self.language.name, self.subproject.__unicode__())

class Unit(models.Model):
    translation = models.ForeignKey(Translation)
    location = models.TextField()
    flags = models.TextField()
    source = models.TextField()
    target = models.TextField()

    def is_plural(self):
        return self.source.find(PLURAL_SEPARATOR) != -1

    def get_source_plurals(self):
        return self.source.split(PLURAL_SEPARATOR)

    def get_target_plurals(self):
        ret = self.target.split(PLURAL_SEPARATOR)
        plurals = self.translation.language.nplurals
        if len(ret) == plurals:
            return ret

        while len(ret) < plurals:
            ret.append('')

        while len(ret) > plurals:
            del(ret[-1])

        return ret
