'''
Fake file to translate messages from django-registration and django.contrib.auth.
'''

def _(s):
    return s

def fake():
    _(u'This username is already taken. Please choose another.')
    _(u'You must type the same password each time')
    _(u'This email address is already in use. Please supply a different email address.')
    _("Old password")
    _("New password")
    _("New password confirmation")
    _("The two password fields didn't match.")
    _("E-mail")
    _("Username")
    _("Password")
    _('Hold down "Control", or "Command" on a Mac, to select more than one.')

    # Javascript messages
    _("Translate using Apertium")
    _("Translate using Microsoft Translator")
    _("Translate using MyMemory")
    _("Sort this column")
    _("AJAX request to load this content has failed!")
    _("Loading...")
    _("Failed translation")
    _("The request for machine translation has failed.")
    _("Error details:")
    _('Confirm resetting repository')
    _('Resetting the repository will throw away all local changes!')
    _('Ok')
    _('Cancel')

