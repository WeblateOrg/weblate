from django.db import models
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.utils.translation import ugettext_lazy as _, gettext
from django.contrib import messages
from django.contrib.auth.models import Group, Permission, User
from django.db.models.signals import post_syncdb

from weblate.lang.models import Language

class Profile(models.Model):
    user = models.ForeignKey(User, unique = True, editable = False)
    language = models.CharField(
        verbose_name = _(u"Interface Language"),
        max_length = 10,
        choices = settings.LANGUAGES
    )
    languages = models.ManyToManyField(
        Language,
        verbose_name = _('Languages'),
        blank = True,
    )
    secondary_languages = models.ManyToManyField(
        Language,
        verbose_name = _('Secondary languages'),
        related_name = 'secondary_profile_set',
        blank = True,
    )
    suggested = models.IntegerField(default = 0, db_index = True)
    translated = models.IntegerField(default = 0, db_index = True)

    def __unicode__(self):
        return self.user.username


@receiver(user_logged_in)
def set_lang(sender, **kwargs):
    request = kwargs['request']
    user = kwargs['user']
    try:
        profile = user.get_profile()
    except Profile.DoesNotExist:
        profile, newprofile = Profile.objects.get_or_create(user = user)
        if newprofile:
            messages.info(request, gettext('Your profile has been migrated, you might want to adjust preferences.'))

    lang_code = user.get_profile().language
    request.session['django_language'] = lang_code

def create_profile_callback(sender, **kwargs):
    '''
    Automatically create profile when creating new user.
    '''
    if kwargs['created']:
        # Create profile
        profile, newprofile = Profile.objects.get_or_create(user = kwargs['instance'])
        if newprofile:
            profile.save

        # Add user to Users group if it exists
        try:
            group = Group.objects.get(name = 'Users')
            kwargs['instance'].groups.add(group)
        except Group.DoesNotExist:
            pass

post_save.connect(create_profile_callback, sender = User)


def create_groups(update, move):
    group, created = Group.objects.get_or_create(name = 'Users')
    if created or update:
        group.permissions.add(
            Permission.objects.get(codename = 'upload_translation'),
            Permission.objects.get(codename = 'overwrite_translation'),
            Permission.objects.get(codename = 'save_translation'),
            Permission.objects.get(codename = 'accept_suggestion'),
            Permission.objects.get(codename = 'delete_suggestion'),
            Permission.objects.get(codename = 'ignore_check'),
            Permission.objects.get(codename = 'upload_dictionary'),
            Permission.objects.get(codename = 'add_dictionary'),
            Permission.objects.get(codename = 'change_dictionary'),
            Permission.objects.get(codename = 'delete_dictionary'),
        )
    group, created = Group.objects.get_or_create(name = 'Managers')
    if created or update:
        group.permissions.add(
            Permission.objects.get(codename = 'author_translation'),
            Permission.objects.get(codename = 'upload_translation'),
            Permission.objects.get(codename = 'overwrite_translation'),
            Permission.objects.get(codename = 'commit_translation'),
            Permission.objects.get(codename = 'update_translation'),
            Permission.objects.get(codename = 'push_translation'),
            Permission.objects.get(codename = 'automatic_translation'),
            Permission.objects.get(codename = 'save_translation'),
            Permission.objects.get(codename = 'accept_suggestion'),
            Permission.objects.get(codename = 'delete_suggestion'),
            Permission.objects.get(codename = 'ignore_check'),
            Permission.objects.get(codename = 'upload_dictionary'),
            Permission.objects.get(codename = 'add_dictionary'),
            Permission.objects.get(codename = 'change_dictionary'),
            Permission.objects.get(codename = 'delete_dictionary'),
        )
    if move:
        for u in User.objects.all():
            u.groups.add(group)

def sync_create_groups(sender, **kwargs):
    if sender.__name__ == 'weblate.accounts.models':
        create_groups(False, False)

post_syncdb.connect(sync_create_groups)
