from django import forms
from django.utils.translation import ugettext_lazy as _

from accounts.models import Profile
from django.contrib.auth.models import User
from registration.forms import RegistrationFormUniqueEmail

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        exclude = [
            'suggested',
            'translated',
            ]

class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'email',
            ]

class ContactForm(forms.Form):
    subject = forms.CharField(label = _('Subject'), required = True)
    name = forms.CharField(label = _('Your name'), required = True)
    email = forms.EmailField(label = _('Your email'), required = True)
    message = forms.CharField(
        label = _('Message'),
        required = True,
        widget = forms.Textarea
    )

class RegistrationForm(RegistrationFormUniqueEmail):
    first_name = forms.CharField(label = _('First name'))
    last_name = forms.CharField(label = _('Last name'))

    def __init__(self, *args, **kwargs):

        super(RegistrationForm, self).__init__(*args, **kwargs)

        self.fields['username'].label = _('Username')
        self.fields['email'].label = _('Email address')
        self.fields['password1'].label = _('Password')
        self.fields['password2'].label = _('Password (again)')

    def save(self, *args, **kwargs):
        new_user = super(RegistrationForm, self).save(*args, **kwargs)
        new_user.first_name = self.cleaned_data['first_name']
        new_user.last_name = self.cleaned_data['last_name']
        new_user.save()
        return new_user
