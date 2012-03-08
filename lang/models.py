from django.db import models
from django.utils.translation import ugettext as _
from django.db.models import Sum

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
        if idx == 0:
            return _('Singular')
        if self.pluralequation in ['(n != 1)', '(n > 1)', 'n > 1']:
            return _('Plural')
        return _('Plural form %d') % idx

    @models.permalink
    def get_absolute_url(self):
        return ('trans.views.show_language', (), {
            'lang': self.code
        })

    def has_translations(self):
        from trans.models import Translation
        return Translation.objects.filter(language = self).count() > 0

    def get_translated_percent(self):
        from trans.models import Translation
        translations = Translation.objects.filter(language = self).aggregate(Sum('translated'), Sum('total'))
        return round(translations['translated__sum'] * 100.0 / translations['total__sum'], 1)
