from django.db import models
from django.utils.translation import ugettext as _

class Language(models.Model):
    code = models.SlugField(unique = True)
    name = models.CharField(max_length = 100)
    nplurals = models.SmallIntegerField(default = 0)
    pluralequation = models.CharField(max_length = 255, blank = True)

    class Meta:
        ordering = ['name']

    def __unicode__(self):
        return self.name

    def get_plural_form(self):
        return 'nplurals=%d; plural=%s;' % (self.nplurals, self.pluralequation)

    def get_plural_label(self, idx):
        '''
        Returns label for plural form.
        '''
        print self.pluralequation
        return _('Plural form %d') % idx
