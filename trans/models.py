from django.db import models
from lang.models import Language

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

class SubProject(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    project = models.ForeignKey(Project)
    repo = models.CharField(max_length = 200)
    branch = models.CharField(max_length = 50)

    @models.permalink
    def get_absolute_url(self):
         return ('trans.views.show_subproject', (), {'project': self.project.slug, 'subproject': self.slug})

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
