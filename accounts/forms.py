from django import forms
from django.utils.translation import ugettext_lazy as _

from accounts.models import Profile
from django.contrib.auth.models import User

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
    message = forms.CharField(
        label = _('Message'),
        required = True,
        widget = forms.Textarea
    )

