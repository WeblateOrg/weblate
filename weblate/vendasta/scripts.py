# -*- coding: utf-8 -*-
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout
from django import forms
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.forms import AddonFormMixin
from weblate.logger import LOGGER
from weblate.trans.forms import UserField


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
        LOGGER.debug("Component from instance: %s", self.instance.component.name)
        LOGGER.debug(
            "User saved to config: %s", self.instance.configuration.get_value("user")
        )
