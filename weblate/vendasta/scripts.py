# -*- coding: utf-8 -*-
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.forms import AddonFormMixin
from weblate.auth.models import User
from weblate.trans.models.change import Change


class UserField(forms.CharField):
    def clean(self, value):
        if not value:
            return None
        try:
            return User.objects.get(Q(username=value) | Q(email=value)).username
        except User.DoesNotExist:
            raise ValidationError(_("No matching user found."))
        except User.MultipleObjectsReturned:
            raise ValidationError(_("More users matched."))


class ApplyTranslationsFromHistoryForm(forms.Form):
    """Select a user for historical translations."""

    user = UserField(
        label=_("User for translations"),
        help_text=_(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )

    def __init__(self, *args, **kwargs):
        """Generate choices for other component in same project."""
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            Field("user"),
        )


class ApplyTranslationsFromHistoryAddonForm(ApplyTranslationsFromHistoryForm, AddonFormMixin):
    def __init__(self, addon, instance=None, *args, **kwargs):
        self._addon = addon
        super().__init__(*args, **kwargs)


class ApplyTranslationsFromHistory(BaseAddon):
    """Triggers on configure and component update."""

    events = ()
    name = "weblate.vendasta.applytranslationsfromhistory"
    verbose = "Apply Translations From History"
    description = "This addon applies the most recent translations from a given user from component history."
    trigger_update = True
    settings_form = ApplyTranslationsFromHistoryAddonForm
    icon = "script.svg"

    def post_configure(self):
        """Apply translations from history after configuring this addon."""
        super(ApplyTranslationsFromHistory, self).post_configure()
        self.apply_translations_from_history()

    def apply_translations_from_history(self):
        """Apply translations from history."""
        user_form_value = self.instance.configuration("user")
        user = User.objects.get(Q(username=user_form_value) | Q(email=user_form_value))

        for change in Change.objects.prefetch().filter(
            Q(project_id__in=user.allowed_project_ids)
            & Q(component=self.instance.component)
            & (
                Q(component__restricted=False)
                | Q(component_id__in=user.component_permissions)
            )
        ).order_by("timestamp"):
            change.save()
