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
        self.fields['username'].help_text = _('At least five characters long')
        self.fields['email'].label = _('Email address')
        self.fields['email'].help_text = _('Activation email will be sent here')
        self.fields['password1'].label = _('Password')
        self.fields['password1'].help_text = _('At least six characters long')
        self.fields['password2'].label = _('Password (again)')
        self.fields['password2'].help_text = _('Repeat the password so we can verify you typed it in correctly')

    def save(self, *args, **kwargs):
        new_user = super(RegistrationForm, self).save(*args, **kwargs)
        new_user.first_name = self.cleaned_data['first_name']
        new_user.last_name = self.cleaned_data['last_name']
        new_user.save()
        return new_user

    def clean_password1(self):
        if len(self.cleaned_data['password1']) < 6:
            raise forms.ValidationError(_(u'Passwords needs to have at least six characters.'))
        return self.cleaned_data['password1']

    def clean_username(self):
        if len(self.cleaned_data['username']) < 5:
            raise forms.ValidationError(_(u'Username needs to have at least five characters.'))
        return super(RegistrationForm, self).clean_username()
