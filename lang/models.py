from django.db import models

class Language(models.Model):
    code = models.SlugField(db_index = True)
    name = models.CharField(max_length = 100)
    nplurals = models.SmallIntegerField(default = 0)
    pluralequation = models.CharField(max_length = 255, blank = True)

    def __unicode__(self):
        return self.name

    def get_plural_form(self):
        return 'nplurals=%d; plural=%s;' % (self.nplurals, self.pluralequation)
