from django.db import models

from lang.models import Language

from util import is_plural, split_plural, join_plural

class TranslationManager(models.Manager):
    def update_from_blob(self, subproject, code, path, blob):
        '''
        Parses translation meta info and creates/updates translation object.
        '''
        lang = Language.objects.get(code = code)
        trans, created = self.get_or_create(
            language = lang,
            subproject = subproject,
            filename = path)
        trans.update_from_blob(blob)

class UnitManager(models.Manager):
    def update_from_unit(self, translation, unit):
        '''
        Process translation toolkit unit and stores/updates database entry.
        '''
        src = join_plural(unit.source.strings)
        ctx = unit.getcontext()
        import trans.models
        try:
            dbunit = self.get(
                translation = translation,
                source = src,
                context = ctx)
            force = False
        except:
            dbunit = trans.models.Unit(
                translation = translation,
                source = src,
                context = ctx)
            force = True

        dbunit.update_from_unit(unit, force)
        return dbunit
