from django.db import models

from lang.models import Language

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

