from django.db import models
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _

from lang.models import Language

class Profile(models.Model):
    user = models.ForeignKey(User, unique = True, editable = False)
    language = models.CharField(
        verbose_name = _(u"Interface Language"),
        max_length = 10,
        choices = settings.LANGUAGES
    )
    languages = models.ManyToManyField(
        Language,
        verbose_name = _('Languages')
    )
    secondary_languages = models.ManyToManyField(
        Language,
        verbose_name = _('Secondary languages'),
        related_name = 'secondary_profile_set'
    )
    suggested = models.IntegerField(default = 0, db_index = True)
    translated = models.IntegerField(default = 0, db_index = True)


@receiver(user_logged_in)
def set_lang(sender, **kwargs):
    lang_code = kwargs['user'].get_profile().language
    kwargs['request'].session['django_language'] = lang_code

def create_profile_callback(sender, **kwargs):
    '''
    Automatically create profile when creating new user.
    '''
    if kwargs['created']:
        profile, newprofile = Profile.objects.get_or_create(user = kwargs['instance'])
        if newprofile:
            profile.save

post_save.connect(create_profile_callback, sender = User)
