from django.db import models
from django.utils.translation import ugettext as _
from django.db.models import Sum

class LanguageManager(models.Manager):
    def auto_create(self, code):
        '''
        Autmatically creates new language based on code and best guess
        of parameters.
        '''
        # Create standard language
        lang = Language.objects.create(
            code = code,
            name = '%s (generated)' % code,
            nplurals = 2,
            pluralequation = '(n != 1)',
        )
        # In case this is just a different variant of known language, get params from that
        if '_' in code:
            try:
                baselang = Language.objects.get(code = code.split('_')[0])
                lang.name = '%s (generated - %s)' % (
                    baselang.name,
                    code,
                )
                lang.nplurals = baselang.nplurals
                lang.pluralequation = baselang.pluralequation
                lang.save()
            except Language.DoesNotExist:
                pass
        return lang

class Language(models.Model):
    code = models.SlugField(unique = True)
    name = models.CharField(max_length = 100)
    nplurals = models.SmallIntegerField(default = 0)
    pluralequation = models.CharField(max_length = 255, blank = True)

    objects = LanguageManager()

    class Meta:
        ordering = ['name']

    def __unicode__(self):
        return _(self.name)

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
