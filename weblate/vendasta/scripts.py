# -*- coding: utf-8 -*-
from django import forms
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.forms import AddonFormMixin
from weblate.logger import LOGGER
from weblate.trans.forms import UserField


class ApplyTranslationsFromHistoryAddonForm(forms.Form, AddonFormMixin):
    """Select a user for historical translations."""

    user = UserField(
        label=_("User for translations"),
        help_text=_(
            "Please type in an existing Weblate account name or e-mail address."
        ),
    )


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
        LOGGER.error("Component from instance: %s", self.instance.component.name)
        LOGGER.error(
            "User saved to config: %s", self.instance.configuration.get_value("user")
        )
