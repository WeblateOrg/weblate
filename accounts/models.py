from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save


class Profile(models.Model):
    user = models.ForeignKey(User, unique = True)

def create_profile_callback(sender, **kwargs):
    '''
    Automatically create profile when creating new user.
    '''
    if kwargs['created']:
        profile, newprofile = Profile.objects.get_or_create(user = kwargs['instance'])
        if newprofile:
            profile.save

post_save.connect(create_profile_callback, sender = User)
